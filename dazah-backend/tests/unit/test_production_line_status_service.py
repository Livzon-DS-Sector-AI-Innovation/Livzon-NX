"""产线停产状态服务单测（状态映射查询 + upsert 设置）。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.production import fermentation_board_service as board


def _session_with_scalars(rows: list[Any]) -> Any:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.anyio
async def test_get_line_halted_map_returns_status_by_product() -> None:
    rows = [
        SimpleNamespace(product_code="MC", halted=True),
        SimpleNamespace(product_code="DR", halted=False),
    ]
    session = _session_with_scalars(rows)

    assert await board.get_line_halted_map(session) == {
        "MC": True,
        "DR": False,
    }


@pytest.mark.anyio
async def test_get_line_halted_map_empty_when_no_rows() -> None:
    session = _session_with_scalars([])

    assert await board.get_line_halted_map(session) == {}


@pytest.mark.anyio
async def test_set_line_halted_creates_when_missing() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    item = await board.set_line_halted(
        session, product_code="MC", halted=True, updated_by="u-1"
    )

    # 状态行 + 时间线事件各一条
    added = [call.args[0] for call in session.add.call_args_list]
    assert len(added) == 2
    created, event = added
    assert created.product_code == "MC"
    assert created.halted is True
    assert created.updated_by == "u-1"
    assert item is created
    assert event.product_code == "MC"
    assert event.halted is True


@pytest.mark.anyio
async def test_set_line_halted_updates_existing() -> None:
    existing = SimpleNamespace(
        id=uuid.uuid4(), product_code="MC", halted=True, updated_by=None
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    item = await board.set_line_halted(
        session, product_code="MC", halted=False, updated_by="u-2"
    )

    # 状态行已存在不重建，仅追加时间线事件
    session.add.assert_called_once()
    assert existing.halted is False
    assert existing.updated_by == "u-2"
    assert item is existing
    assert session.add.call_args.args[0].halted is False


@pytest.mark.anyio
async def test_set_line_halted_appends_event_with_reason_and_operator() -> None:
    """切换一次记一条时间线事件：动作/原因（去空格）/操作人入事件表。"""
    from app.modules.production.models import LineHaltEvent

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    await board.set_line_halted(
        session,
        product_code="LV",
        halted=True,
        updated_by="u-9",
        reason="  转产美伐  ",
        operator_name=" 张三 ",
    )

    event = session.add.call_args_list[-1].args[0]
    assert isinstance(event, LineHaltEvent)
    assert event.product_code == "LV"
    assert event.halted is True
    assert event.reason == "转产美伐"
    assert event.operator_name == "张三"
    assert event.created_by == "u-9"


@pytest.mark.anyio
async def test_latest_line_halt_events_picks_newest_per_product() -> None:
    """按 created_at 倒序回放：每条产线取第一条（即最近一次）。"""
    rows = [
        SimpleNamespace(
            product_code="LV", reason="second", created_at="2026-09-02"
        ),
        SimpleNamespace(
            product_code="LV", reason="first", created_at="2026-09-01"
        ),
        SimpleNamespace(
            product_code="MC", reason="mc", created_at="2026-09-03"
        ),
    ]
    session = _session_with_scalars(rows)

    latest = await board.latest_line_halt_events(session, ["LV", "MC"])
    assert latest["LV"].reason == "second"
    assert latest["MC"].reason == "mc"

    # 空产品列表直接返回，不查库
    empty_session = AsyncMock()
    assert await board.latest_line_halt_events(empty_session, []) == {}
    empty_session.execute.assert_not_awaited()


def test_production_line_codes_cover_all_board_products() -> None:
    """停产状态白名单须覆盖看板全部产线代码（含 LN 盐酸林可霉素），
    否则状态切换接口会报「未知的产品代码」。"""
    assert board.PRODUCTION_LINE_CODES == frozenset(
        {"FA", "MC", "LN", "DR", "LV", "MV", "TY", "FL"}
    )
