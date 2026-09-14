"""发酵车间看板端点集成测试。

- HTTP 层：真实路由；服务层 DB 调用 mock（conftest 共享回滚会话不承载
  真实查询，任何事务都会在其 teardown 触发跨事件循环错误）。
- 真库冒烟：测试体内自建会话走检修 CRUD 与看板加载。

认证：override get_current_user 提供内存管理员。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

import app.platform.identity.rbac as identity_rbac
from app.main import app
from app.modules.production import fermentation_board_service as board
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API = "/api/v1/production"


def _fake_maintenance(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "tank_no": "302A",
        "reason": "滤芯更换",
        "started_at": "2026-09-08T08:00:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def mock_db_service(monkeypatch: Any) -> None:
    """HTTP 层不触碰数据库。"""
    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(board, "load_latest_archive", AsyncMock(return_value=None))
    monkeypatch.setattr(board, "list_active_maintenance", AsyncMock(return_value=[]))
    monkeypatch.setattr(board, "upsert_maintenance", AsyncMock())
    monkeypatch.setattr(board, "delete_maintenance", AsyncMock())
    monkeypatch.setattr(board, "get_maintenance", AsyncMock(return_value=None))
    monkeypatch.setattr(board, "list_batch_actuals", AsyncMock(return_value=[]))
    monkeypatch.setattr(board, "get_batch_actual", AsyncMock(return_value=None))
    monkeypatch.setattr(board, "get_month_setting", AsyncMock(return_value=None))
    monkeypatch.setattr(board, "upsert_month_setting", AsyncMock())
    monkeypatch.setattr(
        board, "sum_extraction_daily_reports", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        board,
        "get_warehouse_finished_inbound_kg",
        AsyncMock(return_value=None),
    )


@pytest.fixture
async def auth_client(
    client: AsyncClient, monkeypatch: Any
) -> AsyncIterator[AsyncClient]:
    # 默认按管理员（通配权限）解析工段数据权限，工段矩阵用 stage_perms 覆盖
    monkeypatch.setattr(
        identity_rbac,
        "resolve_user_permissions",
        AsyncMock(return_value=["*"]),
    )

    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="看板测试用户",
            username=f"board-test-{uuid.uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def stage_perms(monkeypatch: Any):
    """设定当前用户的工段数据权限码（覆盖默认通配）。"""

    def _set(perms: list[str]) -> None:
        monkeypatch.setattr(
            identity_rbac,
            "resolve_user_permissions",
            AsyncMock(return_value=perms),
        )

    return _set


@pytest.mark.anyio
async def test_board_returns_no_archive_message(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    response = await auth_client.get(f"{API}/fermentation-board")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"] is None
    assert "排产" in body["message"]


@pytest.mark.anyio
async def test_board_builds_payload_from_latest_archive(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    fake_payload = {
        "now": "2026-09-08T12:00:00",
        "period": {
            "start": "2026-08-27",
            "end": "2026-09-26",
            "label": "8月27日～9月26日",
        },
        "kpis": {
            "month_planned": 31,
            "month_done_planned": 10,
            "running": 2,
            "pending": 5,
        },
        "tanks": [
            {
                "tank_no": "302A",
                "status": "running",
                "batch_no": "FA26234",
                "inoculate_at": "2026-09-06T21:00:00",
                "cultured_hours": 39.0,
                "cycle_hours": 72,
                "dump_at": "2026-09-09T10:00:00",
                "note": "距放罐约 46h",
            }
        ],
        "recent": [],
        "trend": None,
        "alerts": [{"level": "info", "text": "车间运行正常，无待处理预警"}],
    }
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(board, "build_board", MagicMock(return_value=fake_payload))

    response = await auth_client.get(f"{API}/fermentation-board")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kpis"]["month_planned"] == 31
    assert data["tanks"][0]["tank_no"] == "302A"
    assert "is_current_period" in data


@pytest.mark.anyio
async def test_board_historical_period_view(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    """历史周期：按真实当前时间回看（不回到周期末）、不读取检修、产量按周期过滤。"""
    # 选一个必然早于今天的周期（今天 >= 2026-09 时 2026-05 周期必为历史）
    _patch_period(monkeypatch, date(2026, 4, 27), date(2026, 5, 26))
    build_mock = MagicMock(return_value={"kpis": {}, "period": {}})
    monkeypatch.setattr(board, "build_board", build_mock)

    response = await auth_client.get(f"{API}/fermentation-board?date=2026-05-10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_current_period"] is False
    as_of = build_mock.call_args.args[2]
    # as_of 为真实当前时间（而非周期末 2026-05-26）
    assert as_of > datetime(2026, 9, 1)
    # 历史视图不加载当前检修标注
    board.list_active_maintenance.assert_not_called()
    # 产量列表按周期边界查询
    kwargs = board.list_batch_actuals.call_args.kwargs
    assert kwargs["period_start"] == date(2026, 4, 27)
    assert kwargs["period_end"] == date(2026, 5, 26)


def _patch_period(monkeypatch: Any, start: date, end: date) -> None:
    """让看板端点按指定周期解析（mock 存档与周期定位）。"""
    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(return_value=SimpleNamespace(rows=[])),
    )
    monkeypatch.setattr(
        board,
        "find_period_block",
        MagicMock(
            return_value={
                "start_row": 0,
                "start": start,
                "end": end,
                "label": f"{start.month}月{start.day}日～{end.month}月{end.day}日",
            }
        ),
    )


@pytest.mark.anyio
async def test_board_passes_actuals_to_build_board(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board,
        "list_batch_actuals",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id="1",
                    batch_no="FA26232",
                    dump_date=None,
                    yield_kg=88.5,
                    extract_kg=None,
                    remark=None,
                )
            ]
        ),
    )
    build_mock = MagicMock(return_value={"kpis": {}})
    monkeypatch.setattr(board, "build_board", build_mock)

    response = await auth_client.get(f"{API}/fermentation-board")
    assert response.status_code == 200
    assert build_mock.call_args.kwargs["actuals"][0]["batch_no"] == "FA26232"


@pytest.mark.anyio
async def test_month_capacity_set_and_board_carries(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    # 设置端点：周期来自最新存档
    monkeypatch.setattr(
        board,
        "load_latest_archive",
        AsyncMock(return_value=SimpleNamespace(rows=[])),
    )
    monkeypatch.setattr(board, "current_period", MagicMock(return_value=None))
    rejected = await auth_client.post(
        f"{API}/fermentation-month-capacity",
        json={"planned_capacity_kg": 930000},
    )
    assert rejected.status_code == 400

    from datetime import date

    monkeypatch.setattr(
        board,
        "current_period",
        MagicMock(return_value=(date(2026, 8, 27), date(2026, 9, 26))),
    )
    setting = SimpleNamespace(
        id="s1",
        period_start=date(2026, 8, 27),
        period_end=date(2026, 9, 26),
        planned_capacity_kg=930000.0,
    )
    monkeypatch.setattr(board, "upsert_month_setting", AsyncMock(return_value=setting))
    saved = await auth_client.post(
        f"{API}/fermentation-month-capacity",
        json={"planned_capacity_kg": 930000},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["planned_capacity_kg"] == 930000.0
    kwargs = board.upsert_month_setting.call_args.kwargs
    assert kwargs["period_start"] == date(2026, 8, 27)
    assert kwargs["planned_capacity_kg"] == 930000

    # 看板带出产能
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board,
        "build_board",
        MagicMock(
            return_value={
                "kpis": {},
                "period": {"start": "2026-08-27", "end": "2026-09-26", "label": ""},
            }
        ),
    )
    monkeypatch.setattr(board, "get_month_setting", AsyncMock(return_value=setting))
    res = await auth_client.get(f"{API}/fermentation-board")
    assert res.status_code == 200
    assert res.json()["data"]["month_planned_capacity_kg"] == 930000.0


@pytest.mark.anyio
async def test_batch_actuals_list_filtered_by_period(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    listed = await auth_client.get(
        f"{API}/fermentation-batch-actuals"
        "?period_start=2026-08-27&period_end=2026-09-26"
    )
    assert listed.status_code == 200
    kwargs = board.list_batch_actuals.call_args.kwargs
    assert kwargs["period_start"] == date(2026, 8, 27)
    assert kwargs["period_end"] == date(2026, 9, 26)


@pytest.mark.anyio
async def test_batch_actuals_crud_endpoints(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    item = SimpleNamespace(
        id="x",
        batch_no="FA26232",
        dump_date=date(2026, 9, 9),
        yield_kg=100.0,
        extract_kg=None,
        remark="染菌批",
    )
    monkeypatch.setattr(board, "list_batch_actuals", AsyncMock(return_value=[item]))
    monkeypatch.setattr(board, "upsert_batch_actual", AsyncMock(return_value=item))

    listed = await auth_client.get(f"{API}/fermentation-batch-actuals")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["batch_no"] == "FA26232"
    assert "tank_no" in listed.json()["data"][0]

    saved = await auth_client.post(
        f"{API}/fermentation-batch-actuals",
        json={
            "batch_no": "FA26232",
            "dump_date": "2026-09-09",
            "yield_kg": 100.0,
            "remark": "染菌批",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["yield_kg"] == 100.0
    assert saved.json()["data"]["remark"] == "染菌批"
    assert board.upsert_batch_actual.call_args.kwargs["batch_no"] == "FA26232"
    assert board.upsert_batch_actual.call_args.kwargs["remark"] == "染菌批"

    monkeypatch.setattr(board, "get_batch_actual", AsyncMock(return_value=item))
    monkeypatch.setattr(board, "delete_batch_actual", AsyncMock())
    delete_id = uuid.uuid4()
    deleted = await auth_client.delete(f"{API}/fermentation-batch-actuals/{delete_id}")
    assert deleted.status_code == 200

    monkeypatch.setattr(board, "get_batch_actual", AsyncMock(return_value=None))
    missing_id = uuid.uuid4()
    missing = await auth_client.delete(f"{API}/fermentation-batch-actuals/{missing_id}")
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_maintenance_mark_list_release_via_mock(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    client = auth_client
    item_id = str(uuid.uuid4())

    async def _fake_upsert(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            id=item_id,
            tank_no="302A",
            reason="滤芯更换",
            started_at=datetime(2026, 9, 8, 8, 0, 0),
        )

    board.upsert_maintenance.side_effect = _fake_upsert
    marked = await client.post(
        f"{API}/tank-maintenance",
        json={"tank_no": "302A", "reason": "滤芯更换"},
    )
    assert marked.status_code == 200
    assert marked.json()["data"]["id"] == item_id
    assert marked.json()["data"]["reason"] == "滤芯更换"

    listed = await client.get(f"{API}/tank-maintenance")
    assert listed.status_code == 200


@pytest.mark.anyio
async def test_maintenance_delete_404(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    missing = str(uuid.uuid4())
    deleted = await auth_client.delete(f"{API}/tank-maintenance/{missing}")
    assert deleted.status_code == 404


@pytest.mark.anyio
async def test_maintenance_rejects_empty_reason(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    response = await auth_client.post(
        f"{API}/tank-maintenance",
        json={"tank_no": "302A", "reason": ""},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_batch_actuals_isolated_by_product() -> None:
    """同一批号在不同产品下各自独立（数据隔离），互不覆盖。"""
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            fa = await board.upsert_batch_actual(
                session, batch_no="FA-ISO", yield_kg=111, product_code="FA"
            )
            mc = await board.upsert_batch_actual(
                session, batch_no="FA-ISO", yield_kg=222, product_code="MC"
            )
            assert fa.id != mc.id
            fa_list = await board.list_batch_actuals(session, product_code="FA")
            mc_list = await board.list_batch_actuals(session, product_code="MC")
            assert [i.yield_kg for i in fa_list if i.batch_no == "FA-ISO"] == [111]
            assert [i.yield_kg for i in mc_list if i.batch_no == "FA-ISO"] == [222]
            # 清理
            await board.delete_batch_actual(session, fa)
            await board.delete_batch_actual(session, mc)
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_service_persistence_roundtrip() -> None:
    """真库冒烟：检修标注 upsert → list → delete（自建会话，避免跨循环）。"""
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            item = await board.upsert_maintenance(
                session, tank_no="303A", reason="仪表校验"
            )
            assert item.tank_no == "303A"
            item_id = item.id

            # 同罐重复标记 → 更新
            again = await board.upsert_maintenance(
                session, tank_no="303A", reason="仪表校验-复查"
            )
            assert again.id == item_id
            assert again.reason == "仪表校验-复查"

            active = await board.list_active_maintenance(session)
            assert any(m.id == item_id for m in active)

            fetched = await board.get_maintenance(session, item_id)
            assert fetched is not None
            await board.delete_maintenance(session, fetched)
            assert await board.get_maintenance(session, item_id) is None

            # 看板加载：测试库无存档 → None（端点分支已覆盖消息）
            assert await board.load_latest_archive(session) is None
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_board_block_missing_returns_coverage_hint(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    """存档行解析不出周期块时提示补充排产表。"""
    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(return_value=SimpleNamespace(rows=[["占位行"]], product_code="FA")),
    )
    res = await auth_client.get(f"{API}/fermentation-board?date=2026-09-01")
    assert res.status_code == 200
    assert res.json()["data"] is None
    assert "排产表未覆盖" in res.json()["message"]
    assert board.load_archive_covering.call_args.args[1] == date(2026, 9, 1)


@pytest.mark.anyio
async def test_board_returns_hint_when_payload_unbuildable(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    """find_period_block 命中但 build_board 返回 None 时返回兜底提示。"""
    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(
            return_value=SimpleNamespace(
                rows=[
                    [
                        "2026年08月27日～2026年09月26日103车间FA450T罐排产",
                        "",
                        "",
                    ]
                ],
                product_code="FA",
            )
        ),
    )
    monkeypatch.setattr(board, "build_board", MagicMock(return_value=None))
    res = await auth_client.get(f"{API}/fermentation-board")
    assert res.status_code == 200
    assert res.json()["data"] is None
    assert "排产 Excel" in res.json()["message"]


@pytest.mark.anyio
async def test_maintenance_release_success_path(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
) -> None:
    item = SimpleNamespace(id=uuid.uuid4(), tank_no="302A", reason="滤芯更换")
    monkeypatch.setattr(board, "get_maintenance", AsyncMock(return_value=item))
    monkeypatch.setattr(board, "delete_maintenance", AsyncMock())
    res = await auth_client.delete(f"{API}/tank-maintenance/{item.id}")
    assert res.status_code == 200
    assert "已解除检修" in res.json()["message"]
    assert board.delete_maintenance.call_args.args[1] is item


@pytest.mark.anyio
async def test_month_capacity_requires_existing_archive(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    """无存档时设置产能返回 400（夹具默认无存档）。"""
    res = await auth_client.post(
        f"{API}/fermentation-month-capacity",
        json={"planned_capacity_kg": 100000},
    )
    assert res.status_code == 400
    assert "尚未上传排产 Excel" in res.json()["message"]


# ═══════════════════ 工段数据权限（发酵/提炼） ═══════════════════


def _full_board_payload() -> dict[str, Any]:
    return {
        "now": "2026-09-11T12:00:00",
        "period": {
            "start": "2026-08-27",
            "end": "2026-09-26",
            "label": "8月27日～9月26日",
        },
        "kpis": {"month_planned": 31, "month_done_yield_kg": 449600.0},
        "tanks": [{"tank_no": "302A", "status": "running"}],
        "recent": [
            {
                "batch_no": "FA26233",
                "yield_kg": 100.0,
                "extract_kg": 88.0,
                "batch_yield_rate": 88.0,
            }
        ],
        "trend": {"batches": ["FA26233"], "outputs": [100.0]},
        "dumped_batches": [{"batch_no": "FA26233"}],
        "extraction": {
            "ferment_total_kg": 100.0,
            "extract_total_kg": 88.0,
            "rate_realtime": 88.0,
            "rate_paired": 88.0,
        },
        "alerts": [{"level": "info", "text": "车间运行正常，无待处理播报"}],
        "maintenance": [],
    }


@pytest.mark.anyio
async def test_board_hides_extraction_without_extract_permission(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """发酵岗：发酵模块全可见；提炼汇总与单批提炼字段不出接口。"""
    stage_perms(["production:fermentation-yield"])
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )

    res = await auth_client.get(f"{API}/fermentation-board")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kpis"]["month_planned"] == 31
    assert data["tanks"][0]["tank_no"] == "302A"
    assert data["extraction"] is None
    assert data["recent"][0]["yield_kg"] == 100.0
    assert "extract_kg" not in data["recent"][0]
    assert "batch_yield_rate" not in data["recent"][0]


@pytest.mark.anyio
async def test_board_hides_fermentation_without_ferm_permission(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """提炼岗：仅提炼汇总可见，发酵模块字段不出接口。"""
    stage_perms(["production:extraction-yield"])
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )
    monkeypatch.setattr(
        board,
        "get_month_setting",
        AsyncMock(return_value=SimpleNamespace(planned_capacity_kg=930000.0)),
    )
    # 「提炼已出成品」以成品日报为唯一数据源：返回当期日报记录
    monkeypatch.setattr(
        board, "sum_extraction_daily_reports", AsyncMock(return_value=[88.0])
    )

    res = await auth_client.get(f"{API}/fermentation-board")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kpis"] is None
    assert data["tanks"] == []
    assert data["recent"] == []
    assert data["trend"] is None
    assert data["maintenance"] == []
    assert data["month_planned_capacity_kg"] is None
    # 已放罐批次下拉属排产信息，提炼岗录入时同样需要
    assert data["dumped_batches"] == [{"batch_no": "FA26233"}]
    assert data["extraction"]["extract_total_kg"] == 88.0
    assert data["extraction"]["extract_batches"] == 1
    # 提炼岗能看到跑马灯（排产节奏信息，非产量数据）
    assert data["alerts"]


@pytest.mark.anyio
async def test_board_full_view_with_both_permissions(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """领导（双权限）：全部数据可见。"""
    stage_perms(
        ["production:fermentation-yield", "production:extraction-yield"]
    )
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )

    res = await auth_client.get(f"{API}/fermentation-board")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["kpis"]["month_planned"] == 31
    assert data["extraction"]["rate_paired"] == 88.0
    assert data["recent"][0]["extract_kg"] == 88.0
    assert data["recent"][0]["batch_yield_rate"] == 88.0


@pytest.mark.anyio
async def test_board_carries_warehouse_inbound_for_extract_permission(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """提炼权限 + 已接入产品：看板携带当期仓储入库合计。"""
    stage_perms(["production:extraction-yield"])
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )
    inbound_mock = AsyncMock(return_value=410490.0)
    monkeypatch.setattr(
        board, "get_warehouse_finished_inbound_kg", inbound_mock
    )

    res = await auth_client.get(f"{API}/fermentation-board?product=FA")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["extract_finished_inbound_kg"] == 410490.0
    # 取数跟随所选扎帐周期与产品上下文
    assert inbound_mock.call_args.kwargs["product_code"] == "FA"
    assert inbound_mock.call_args.kwargs["period_start"] == date(2026, 8, 27)
    assert inbound_mock.call_args.kwargs["period_end"] == date(2026, 9, 26)


@pytest.mark.anyio
async def test_board_warehouse_inbound_hidden_without_extract_permission(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """无提炼权限：仓储入库合计不出接口（卡片本就不可见）。"""
    stage_perms(["production:fermentation-yield"])
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )
    inbound_mock = AsyncMock(return_value=410490.0)
    monkeypatch.setattr(
        board, "get_warehouse_finished_inbound_kg", inbound_mock
    )

    res = await auth_client.get(f"{API}/fermentation-board?product=FA")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["extract_finished_inbound_kg"] is None
    inbound_mock.assert_not_called()


@pytest.mark.anyio
async def test_board_warehouse_inbound_none_for_unwired_product(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """未接入产品（真实映射）：衔接函数返回 None，卡片维持待接入。"""
    stage_perms(["production:extraction-yield"])
    _patch_period(monkeypatch, date(2026, 8, 27), date(2026, 9, 26))
    monkeypatch.setattr(
        board, "build_board", MagicMock(return_value=_full_board_payload())
    )

    res = await auth_client.get(f"{API}/fermentation-board?product=MC")
    assert res.status_code == 200
    assert res.json()["data"]["extract_finished_inbound_kg"] is None


@pytest.mark.anyio
async def test_actuals_list_filters_stage_fields(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """历史数据列表按工段权限过滤字段。"""
    item = SimpleNamespace(
        id="x",
        batch_no="FA26232",
        dump_date=date(2026, 9, 9),
        yield_kg=100.0,
        extract_kg=88.0,
        remark="染菌批",
    )
    monkeypatch.setattr(board, "list_batch_actuals", AsyncMock(return_value=[item]))

    stage_perms(["production:fermentation-yield"])
    ferm_view = await auth_client.get(f"{API}/fermentation-batch-actuals")
    row = ferm_view.json()["data"][0]
    assert row["yield_kg"] == 100.0
    assert "extract_kg" not in row

    stage_perms(["production:extraction-yield"])
    extract_view = await auth_client.get(f"{API}/fermentation-batch-actuals")
    row = extract_view.json()["data"][0]
    assert "yield_kg" not in row
    assert row["extract_kg"] == 88.0
    assert row["batch_no"] == "FA26232"


@pytest.mark.anyio
async def test_upsert_rejects_cross_stage_field_writes(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """无对应工段权限时禁止写入对方字段（403），且不触达服务层。"""
    monkeypatch.setattr(board, "upsert_batch_actual", AsyncMock())
    body = {"batch_no": "FA26234", "yield_kg": 100.0}
    stage_perms(["production:extraction-yield"])
    denied = await auth_client.post(f"{API}/fermentation-batch-actuals", json=body)
    assert denied.status_code == 403
    assert "发酵" in denied.json()["message"]
    board.upsert_batch_actual.assert_not_called()

    stage_perms(["production:fermentation-yield"])
    denied = await auth_client.post(
        f"{API}/fermentation-batch-actuals",
        json={"batch_no": "FA26234", "extract_kg": 88.0},
    )
    assert denied.status_code == 403
    board.upsert_batch_actual.assert_not_called()


@pytest.mark.anyio
async def test_upsert_passes_provided_fields_and_filters_response(
    auth_client: AsyncClient,
    mock_db_service: None,
    monkeypatch: Any,
    stage_perms,
) -> None:
    """允许时按显式字段更新，响应按权限过滤。"""
    saved = SimpleNamespace(
        id="x",
        batch_no="FA26234",
        dump_date=None,
        yield_kg=None,
        extract_kg=88.0,
        remark=None,
    )
    monkeypatch.setattr(board, "upsert_batch_actual", AsyncMock(return_value=saved))

    # 提炼岗只提交提炼字段 → 放行且 provided_fields 不含发酵字段
    stage_perms(["production:extraction-yield"])
    ok = await auth_client.post(
        f"{API}/fermentation-batch-actuals",
        json={"batch_no": "FA26234", "extract_kg": 88.0},
    )
    assert ok.status_code == 200
    kwargs = board.upsert_batch_actual.call_args.kwargs
    assert kwargs["provided_fields"] == {"extract_kg"}
    assert ok.json()["data"]["extract_kg"] == 88.0
    assert "yield_kg" not in ok.json()["data"]

    # 发酵岗提交发酵字段组 → 放行
    stage_perms(["production:fermentation-yield"])
    ok = await auth_client.post(
        f"{API}/fermentation-batch-actuals",
        json={"batch_no": "FA26234", "yield_kg": 100.0, "remark": "正常"},
    )
    assert ok.status_code == 200
    kwargs = board.upsert_batch_actual.call_args.kwargs
    assert kwargs["provided_fields"] == {"yield_kg", "remark"}


@pytest.mark.anyio
async def test_upsert_rejects_empty_stage_fields(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    """只有批号、无任何产量字段时拒绝保存。"""
    res = await auth_client.post(
        f"{API}/fermentation-batch-actuals", json={"batch_no": "FA26234"}
    )
    assert res.status_code == 400
    assert "产量字段" in res.json()["message"]


@pytest.mark.anyio
async def test_partial_upsert_preserves_other_stage_data() -> None:
    """真库冒烟：按 provided_fields 部分更新，跨工段数据互不清除。"""
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # 提炼岗视角：仅录提炼成品
            item = await board.upsert_batch_actual(
                session,
                batch_no="FA-STAGE",
                extract_kg=88.0,
                provided_fields={"extract_kg"},
            )
            assert item.extract_kg == 88.0
            assert item.yield_kg is None

            # 发酵岗视角：仅录放罐产量 → 提炼数据保留
            item = await board.upsert_batch_actual(
                session,
                batch_no="FA-STAGE",
                yield_kg=100.0,
                provided_fields={"yield_kg"},
            )
            assert item.yield_kg == 100.0
            assert item.extract_kg == 88.0

            # 不传 provided_fields 保持旧的全量替换语义
            item = await board.upsert_batch_actual(
                session,
                batch_no="FA-STAGE",
                dump_date=date(2026, 9, 11),
                yield_kg=95.0,
                remark="复核",
            )
            assert item.yield_kg == 95.0
            assert item.extract_kg is None

            await board.delete_batch_actual(session, item)
    finally:
        await engine.dispose()
