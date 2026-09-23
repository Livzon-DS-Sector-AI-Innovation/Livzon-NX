"""氟苯尼考生产看板端点集成测试（入库确认驱动口径）。

HTTP 层：真实路由 + mock 数据库会话与仓储台账行；认证：override
get_current_user 提供内存管理员；工段权限矩阵用 resolve_user_permissions
覆盖。锚点冻结在 2026-09-22 12:00（北京时间）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.platform.identity.rbac as identity_rbac
from app.core.database import get_db
from app.main import app
from app.modules.production import fl_board_api
from app.modules.production.fl_models import FlBatch
from app.modules.production.models import ProductionPlan
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API = "/api/v1/production"

TODAY = date(2026, 9, 22)


def _batch(batch_no: str, **overrides: Any) -> FlBatch:
    defaults: dict[str, Any] = {
        "order_date": None,
        "pick_date": None,
        "charge_date": None,
        "charge_time": None,
        "mix_date": None,
        "mix_time": None,
        "spec": "10kg/袋、2袋/箱",
        "pack_weight_kg": 1980.0,
        "pack_date": None,
        "pack_time": None,
        "inspection_date": None,
        "inbound_date": None,
        "source_table": "9月排产",
        "data_month": "2026-09",
    }
    defaults.update(overrides)
    return FlBatch(batch_no=batch_no, **defaults)


def _month_rows() -> list[FlBatch]:
    """9 月排产 8 批，覆盖五态与滚动窗口边界。"""
    return [
        # 已确认入库（窗口外，9/1–9/2：不进流转表，进明细/最近完成）
        _batch(
            "FL-2609001",
            order_date=date(2026, 8, 31),
            charge_date=date(2026, 9, 1),
            inbound_date=date(2026, 9, 1),
        ),
        _batch(
            "FL-2609002",
            order_date=date(2026, 9, 1),
            charge_date=date(2026, 9, 2),
            inbound_date=date(2026, 9, 2),
        ),
        # 待入库确认（登记未勾）：常驻流转表
        _batch(
            "FL-2609003",
            order_date=date(2026, 9, 2),
            charge_date=date(2026, 9, 3),
            inbound_date=date(2026, 9, 3),
        ),
        # 滞留：计划入库 9/20 已过、台账无登记
        _batch(
            "FL-2609004",
            order_date=date(2026, 9, 19),
            charge_date=date(2026, 9, 20),
            inbound_date=date(2026, 9, 20),
        ),
        # 在制：今日 8:00 投料、计划 9/23 入库
        _batch(
            "FL-2609005",
            order_date=date(2026, 9, 21),
            charge_date=date(2026, 9, 22),
            charge_time="8:00~10:00",
            inbound_date=date(2026, 9, 23),
        ),
        # 待投料（预告窗口内：9/24 08:00 ≤ 锚点+2 天）
        _batch(
            "FL-2609006",
            order_date=date(2026, 9, 23),
            charge_date=date(2026, 9, 24),
            charge_time="8:00~10:00",
            inbound_date=date(2026, 9, 24),
        ),
        # 待投料（窗口外：9/26）
        _batch(
            "FL-2609007",
            order_date=date(2026, 9, 25),
            charge_date=date(2026, 9, 26),
            inbound_date=date(2026, 9, 26),
        ),
        # 已确认入库（窗口内：实际入库 9/21 ≥ 锚点-2 天，保留在流转表）
        _batch(
            "FL-2609008",
            order_date=date(2026, 9, 20),
            charge_date=date(2026, 9, 21),
            inbound_date=date(2026, 9, 21),
        ),
    ]


def _warehouse_rows() -> list[dict[str, Any]]:
    """入库台账（明细）行：FL-2609003 未确认；另含一笔 8 月批次验证扎帐月口径。"""
    return [
        {
            "batch_no": "FL-2609001",
            "inbound_date": date(2026, 9, 1),
            "qty": 1980.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2609002",
            "inbound_date": date(2026, 9, 2),
            "qty": 1980.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2609003",
            "inbound_date": date(2026, 9, 3),
            "qty": 1980.0,
            "confirmed": False,
        },
        {
            "batch_no": "FL-2609008",
            "inbound_date": date(2026, 9, 21),
            "qty": 1980.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2608018",
            "inbound_date": date(2026, 8, 27),
            "qty": 1980.0,
            "confirmed": True,
        },
    ]


def _result(rows: list[Any]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
async def board_client(monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    """管理员 + 按查询顺序回放结果的 mock 数据库与仓储台账。"""

    plan_rows = [
        ProductionPlan(
            product_name="2%氟苯尼考预混剂",
            workshop="102-2车间",
            planned_yield=7000.0,
            plan_date=date(2026, 9, 1),
        )
    ]
    db = AsyncMock(spec=AsyncSession)
    # 查询顺序：月批次 → 产销计划 → 最近完成的排产信息
    db.execute = AsyncMock(
        side_effect=[
            _result(_month_rows()),
            _result(plan_rows),
            _result(_month_rows()[:3] + [_batch("FL-2608018")]),
        ]
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db  # type: ignore[misc]

    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="看板测试用户",
            username=f"fl-test-{uuid.uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    monkeypatch.setattr(
        identity_rbac, "resolve_user_permissions", AsyncMock(return_value=["*"])
    )
    monkeypatch.setattr(
        fl_board_api, "_warehouse_rows", AsyncMock(return_value=_warehouse_rows())
    )
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def stage_perms(monkeypatch: Any):
    def _set(perms: list[str]) -> None:
        monkeypatch.setattr(
            identity_rbac,
            "resolve_user_permissions",
            AsyncMock(return_value=perms),
        )

    return _set


def _freeze_now(monkeypatch: Any) -> None:
    """冻结锚点为 2026-09-22 12:00（北京时间）。"""
    from datetime import datetime, timedelta, timezone

    frozen = datetime(
        TODAY.year, TODAY.month, TODAY.day, 12, 0, tzinfo=timezone(timedelta(hours=8))
    )

    class _FrozenDatetime(datetime):  # type: ignore[type-arg]
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN201
            return frozen

    monkeypatch.setattr(fl_board_api, "datetime", _FrozenDatetime)


@pytest.mark.anyio
async def test_fl_board_states_and_rolling_window(
    board_client: AsyncClient, monkeypatch: Any
) -> None:
    _freeze_now(monkeypatch)
    response = await board_client.get(f"{API}/fl-board?month=2026-09")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["batch_prefix"] == "FL-2609"
    assert data["is_current_month"] is True
    assert data["period"]["label"] == "8月27日～9月26日"
    # 计划：产销计划 7000kg / 排产 8 批
    assert data["planned_kg"] == 7000.0
    assert data["planned_batches"] == 8
    # 实际入库（已确认）：扎帐月 8/27–9/26 内 4 批（含 8 月批次 2608018）
    assert data["inbound_batches"] == 4
    assert data["inbound_kg"] == 7920.0
    assert data["completion_rate"] == 113.14
    # 在制口径（已投料未确认入库）：待确认 + 滞留 + 在制 = 3
    assert data["in_progress_count"] == 3
    assert data["progress"]["by_batches"] == {
        "inbound": 3,
        "in_progress": 3,
        "not_started": 2,
    }

    # 滚动窗口（锚点 9/22 12:00 ±2 天）：待确认/滞留/在制常驻 +
    # 已入库保留 2 天（008）+ 待投料预告（006）；001/002 出窗、007 未入窗
    flow = [(b["batch_no"], b["state"]) for b in data["flow"]]
    assert flow == [
        ("FL-2609003", "confirm_pending"),
        ("FL-2609004", "stalled"),
        ("FL-2609008", "inbound"),
        ("FL-2609005", "running"),
        ("FL-2609006", "upcoming"),
    ]
    by_no = {b["batch_no"]: b for b in data["flow"]}
    assert by_no["FL-2609003"]["state_label"] == "待入库确认"
    assert by_no["FL-2609003"]["elapsed_days"] == 19
    assert by_no["FL-2609005"]["stage_label"] == "投料"
    assert by_no["FL-2609008"]["actual_inbound_date"] == "2026-09-21"
    assert by_no["FL-2609006"]["state_label"] == "待投料"

    # 明细（A 口径）：仅已确认批次，按实际入库日期倒序
    assert [b["batch_no"] for b in data["month_batches"]] == [
        "FL-2609008",
        "FL-2609002",
        "FL-2609001",
    ]

    # 最近完成：全产线已确认按实际入库倒序（含 8 月批次）
    assert [b["batch_no"] for b in data["recent_completed"]] == [
        "FL-2609008",
        "FL-2609002",
        "FL-2609001",
        "FL-2608018",
    ]


@pytest.mark.anyio
async def test_fl_board_hides_yield_without_extract_permission(
    board_client: AsyncClient, monkeypatch: Any, stage_perms: Any
) -> None:
    _freeze_now(monkeypatch)
    stage_perms(["production:fermentation-yield"])
    response = await board_client.get(f"{API}/fl-board?month=2026-09")
    assert response.status_code == 200
    data = response.json()["data"]
    # 无提炼（生产）权限：产量类数值与批次重量不下发，状态结构保留
    assert data["planned_kg"] is None
    assert data["inbound_kg"] is None
    assert data["completion_rate"] is None
    assert data["inbound_batches"] == 4
    assert all("pack_weight_kg" not in b for b in data["month_batches"])
    assert all("pack_weight_kg" not in b for b in data["flow"])


@pytest.mark.anyio
async def test_fl_board_rejects_invalid_month(board_client: AsyncClient) -> None:
    response = await board_client.get(f"{API}/fl-board?month=2026-13")
    assert response.status_code == 422
