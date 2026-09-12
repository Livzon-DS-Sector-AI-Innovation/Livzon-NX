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
@pytest.mark.anyio
async def test_run_monthly_analysis_executes_all_groups_and_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """逐组执行：命中入队/未配置跳过/停用线跳过/异常跳过，最后标记 done。"""
    added: list[Any] = []

    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(first=lambda: None)
            )
        ),
        add=lambda row: added.append(row),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        tma,
        "load_inspection_trend_alert_config",
        AsyncMock(
            return_value=InspectionTrendAlertConfig(
                is_enabled=True,
                lines={"qc_finished_internal": {"enabled": True}},
            )
        ),
    )

    async def ok_group(db, **kwargs):
        return {
            "configured": True,
            "source_entity_code": "qc_finished_internal",
            "summary": {"trend_ai_pending_count": 2},
            "charts": [1, 2],
        }

    async def unconfigured_group(db, **kwargs):
        return {"configured": False}

    async def disabled_group(db, **kwargs):
        return {
            "configured": True,
            "source_entity_code": "other_line",
            "summary": {},
            "charts": [1],
        }

    async def broken_group(db, **kwargs):
        raise RuntimeError("boom")

    runners = [
        ("internal", ok_group, {}),
        ("none", unconfigured_group, {}),
        ("disabled", disabled_group, {}),
        ("broken", broken_group, {}),
    ]
    monkeypatch.setattr(tma, "_GROUP_RUNNERS", runners)

    stats = await tma.run_trend_monthly_analysis(db, "2026-09")
    # "other_line" 不在停用名单 → 默认启用并计入 lines/charts
    assert stats == {"lines": 2, "charts": 3, "enqueued": 1, "skipped": 1}
    assert len(added) == 1
    assert added[0].status == "done"
    assert added[0].last_error == "1 组拉取失败"

