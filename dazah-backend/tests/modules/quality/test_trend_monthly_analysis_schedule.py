"""趋势 AI 月度分析调度：到期判定与重复执行短路。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.service import trend_monthly_analysis as tma
from app.modules.quality.service.quality_notification_settings import (
    InspectionTrendAlertConfig,
)


def _db(existing_id: str | None) -> Any:
    row = SimpleNamespace(id=existing_id) if existing_id else None
    inner = SimpleNamespace(
        first=lambda: row, scalars=lambda: SimpleNamespace(first=lambda: row)
    )
    return SimpleNamespace(
        execute=AsyncMock(return_value=inner), add=Mock(), commit=AsyncMock()
    )


@pytest.mark.anyio
async def test_find_due_returns_empty_when_disabled() -> None:
    db = _db(None)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            tma,
            "load_inspection_trend_alert_config",
            AsyncMock(return_value=InspectionTrendAlertConfig(is_enabled=False)),
        )
        assert await tma.find_due_trend_monthly_analysis(db) == []


@pytest.mark.anyio
async def test_find_due_returns_empty_when_period_already_ran() -> None:
    db = _db("run-1")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            tma,
            "load_inspection_trend_alert_config",
            AsyncMock(return_value=InspectionTrendAlertConfig(is_enabled=True)),
        )
        assert await tma.find_due_trend_monthly_analysis(db) == []


@pytest.mark.anyio
async def test_find_due_returns_empty_before_effective_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(None)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 9, 3, 12, 0, 0)

    monkeypatch.setattr(tma, "datetime", _FakeDatetime, raising=False)
    monkeypatch.setattr(
        tma,
        "load_inspection_trend_alert_config",
        AsyncMock(
            return_value=InspectionTrendAlertConfig(is_enabled=True, monthly_day=25)
        ),
    )
    assert await tma.find_due_trend_monthly_analysis(db) == []


@pytest.mark.anyio
async def test_find_due_triggers_on_or_after_effective_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(None)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 9, 25, 12, 0, 0)

    monkeypatch.setattr(tma, "datetime", _FakeDatetime, raising=False)
    monkeypatch.setattr(
        tma,
        "load_inspection_trend_alert_config",
        AsyncMock(
            return_value=InspectionTrendAlertConfig(is_enabled=True, monthly_day=31)
        ),
    )
    # 9 月只有 30 天：effective_day = min(31, 30) = 30，25 日未到
    assert await tma.find_due_trend_monthly_analysis(db) == []

    class _FakeDatetimeEnd(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 9, 30, 12, 0, 0)

    monkeypatch.setattr(tma, "datetime", _FakeDatetimeEnd, raising=False)
    assert await tma.find_due_trend_monthly_analysis(db) == ["2026-09"]


@pytest.mark.anyio
async def test_run_monthly_analysis_short_circuits_when_already_ran() -> None:
    db = _db("run-1")
    result = await tma.run_trend_monthly_analysis(db, "2026-09")
    assert result == {"status": "already"}
    db.add.assert_not_called()
