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
async def test_run_monthly_analysis_executes_all_lines_and_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """逐产品线执行：入队/未配置跳过/停用线跳过/异常跳过，最后标记 done。"""
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
                lines={
                    "qc_finished_internal": {"enabled": True},
                    "qc_finished_off": {"enabled": False},
                },
            )
        ),
    )

    async def ok_line(db, **kwargs):
        return {
            "configured": True,
            "source_entity_code": kwargs.get("source_entity_code"),
            "summary": {"trend_ai_pending_count": 1},
            "charts": [1, 2],
        }

    async def unconfigured_line(db, **kwargs):
        return {"configured": False}

    async def disabled_line(db, **kwargs):
        return {
            "configured": True,
            "source_entity_code": kwargs.get("source_entity_code"),
            "summary": {},
            "charts": [1],
        }

    async def broken_line(db, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        tma,
        "iter_monthly_lines",
        lambda: [
            ("qc_finished_internal", "霉酚酸（内控）", ok_line),
            ("qc_finished_none", "未配置线", unconfigured_line),
            ("qc_finished_off", "停用线", disabled_line),
            ("qc_finished_broken", "故障线", broken_line),
        ],
    )
    # 逐线等待 AI 任务到终态由 _wait_line_ai_job 负责，这里桩掉避免真实轮询
    monkeypatch.setattr(
        tma, "_wait_line_ai_job", AsyncMock(return_value="completed")
    )

    stats = await tma.run_trend_monthly_analysis(db, "2026-09")
    # 停用线与未配置线不计入；故障线计入 skipped；只有内控线入队
    assert stats == {"lines": 1, "charts": 2, "enqueued": 1, "skipped": 1}
    assert len(added) == 1
    assert added[0].status == "done"
    assert added[0].last_error == "1 组拉取失败"


@pytest.mark.anyio
async def test_wait_line_ai_job_retries_failed_then_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """串行等待：failed 无结论 → 自动重试一次，随后 pending → completed 返回。"""
    rows = [
        SimpleNamespace(notification_status="failed", ai_summary=None),
        SimpleNamespace(notification_status="pending", ai_summary=None),
        SimpleNamespace(notification_status="completed", ai_summary={"summary": "ok"}),
    ]
    calls = {"count": 0}

    async def fake_get(db, **_kwargs):
        index = min(calls["count"], len(rows) - 1)
        calls["count"] += 1
        return rows[index]

    monkeypatch.setattr(tma.calc, "_get_existing_trend_ai", fake_get)
    submit = AsyncMock()
    monkeypatch.setattr(tma.calc, "_submit_trend_ai_job", submit)
    monkeypatch.setattr(tma, "_LINE_JOB_POLL_SECONDS", 0)
    db = SimpleNamespace(expire_all=Mock(), commit=AsyncMock())

    status = await tma._wait_line_ai_job(
        db, entity_code="qc_finished_lft_ep", period="2026-09"
    )
    assert status == "completed"
    submit.assert_awaited_once()


@pytest.mark.anyio
async def test_wait_line_ai_job_returns_terminal_without_retry_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已交付（sent）的行不重试，直接返回终态。"""
    row = SimpleNamespace(notification_status="sent", ai_summary={"summary": "ok"})
    monkeypatch.setattr(
        tma.calc, "_get_existing_trend_ai", AsyncMock(return_value=row)
    )
    submit = AsyncMock()
    monkeypatch.setattr(tma.calc, "_submit_trend_ai_job", submit)
    db = SimpleNamespace(expire_all=Mock(), commit=AsyncMock())

    status = await tma._wait_line_ai_job(
        db, entity_code="qc_finished_lft_ep", period="2026-09"
    )
    assert status == "sent"
    submit.assert_not_awaited()

