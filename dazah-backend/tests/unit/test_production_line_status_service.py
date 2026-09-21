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

    session.add.assert_called_once()
    created = session.add.call_args.args[0]
    assert created.product_code == "MC"
    assert created.halted is True
    assert created.updated_by == "u-1"
    assert item is created


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

    session.add.assert_not_called()
    assert existing.halted is False
    assert existing.updated_by == "u-2"
    assert item is existing


def test_production_line_codes_cover_all_board_products() -> None:
    """停产状态白名单须覆盖看板全部产线代码（含 LN 盐酸林可霉素），
    否则状态切换接口会报「未知的产品代码」。"""
    assert board.PRODUCTION_LINE_CODES == frozenset(
        {"FA", "MC", "LN", "DR", "LV", "MV", "TY", "FL"}
    )
