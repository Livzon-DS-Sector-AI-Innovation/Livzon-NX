"""下周期排产未上传提醒（next_period_coverage_alert）单测。"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.production import fermentation_board_service as board

BLOCK = {
    "start": date(2026, 8, 27),
    "end": date(2026, 9, 26),
    "label": "8月27日～9月26日",
}


@pytest.mark.anyio
async def test_alert_fires_within_window_when_next_period_uncovered(
    monkeypatch: Any,
) -> None:
    """剩余 2 天（≤3）且无存档覆盖下周期 → 播报 warn。"""
    monkeypatch.setattr(board, "load_archive_covering", AsyncMock(return_value=None))
    alert = await board.next_period_coverage_alert(
        AsyncMock(), product_code="FA", block=BLOCK, today=date(2026, 9, 24)
    )
    assert alert is not None
    assert alert["level"] == "warn"
    assert "尚无存档覆盖下一周期" in alert["text"]
    # 查询下周期覆盖用的日期 = 周期结束次日
    args = board.load_archive_covering.call_args.args
    assert args[1] == date(2026, 9, 27)
    assert args[2] == "FA"


@pytest.mark.anyio
async def test_alert_silent_when_next_period_covered(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        board, "load_archive_covering", AsyncMock(return_value=object())
    )
    assert (
        await board.next_period_coverage_alert(
            AsyncMock(), product_code="MC", block=BLOCK, today=date(2026, 9, 24)
        )
        is None
    )


@pytest.mark.anyio
async def test_alert_silent_outside_window(monkeypatch: Any) -> None:
    monkeypatch.setattr(board, "load_archive_covering", AsyncMock(return_value=None))
    # 剩余 4 天：未进临期窗口，不查询
    assert (
        await board.next_period_coverage_alert(
            AsyncMock(), product_code="FA", block=BLOCK, today=date(2026, 9, 22)
        )
        is None
    )
    # 周期已结束（历史回看）：静音
    assert (
        await board.next_period_coverage_alert(
            AsyncMock(), product_code="FA", block=BLOCK, today=date(2026, 9, 30)
        )
        is None
    )
    board.load_archive_covering.assert_not_called()
