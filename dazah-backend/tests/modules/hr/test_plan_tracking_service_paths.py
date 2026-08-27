from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.hr import plan_tracking_service


def _item(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "is_deleted": False,
        "training_month": "8月",
        "month": None,
        "sort_order": 1,
        "target_audience_new": "质量全员",
        "target_audience": "旧对象",
        "content_textbook": "偏差处理",
        "content_and_textbook": "旧内容",
        "training_type": "内部培训",
        "assessment_method": "考试",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_sync_period_is_idempotent_and_preserves_manual_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eligible = _item()
    wrong_month = _item(training_month="9")
    deleted = _item(is_deleted=True)
    already_recorded = _item()
    existing = SimpleNamespace(
        id=uuid4(),
        plan_item_id=already_recorded.id,
        actual_time="人工填写",
        sessions_snapshot="系统旧值",
    )
    plan = SimpleNamespace(
        id=uuid4(), department="质量部", items=[eligible, wrong_month, deleted]
    )

    class _Column:
        def in_(self, _values: object) -> object:
            return object()

    class _Record:
        id = _Column()

        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)
            self.id = uuid4()
            self.actual_time = None
            self.sessions_snapshot = None

    class _Update:
        def where(self, *_args: object) -> _Update:
            return self

        def values(self, **_kwargs: object) -> _Update:
            return self

    monkeypatch.setattr(plan_tracking_service, "PlanTrackingRecord", _Record)
    monkeypatch.setattr(plan_tracking_service, "sa_update", lambda *_args: _Update())

    created_records: list[_Record] = []

    async def list_by_period(**_kwargs: object) -> list[object]:
        return [created_records[0], existing] if created_records else []

    async def create(record: _Record) -> _Record:
        created_records.append(record)
        return record

    repo = SimpleNamespace(
        list_by_period=AsyncMock(side_effect=list_by_period),
        create=AsyncMock(side_effect=create),
    )
    session = SimpleNamespace(flush=AsyncMock(), execute=AsyncMock())
    service = plan_tracking_service.PlanTrackingService.__new__(
        plan_tracking_service.PlanTrackingService
    )
    service.repo = repo
    service.session = session
    service._find_period_plans = AsyncMock(return_value=[plan])

    service._aggregate_sessions = AsyncMock(
        return_value={eligible.id: "8月26日 09:00-10:00"}
    )

    result = await service.sync_period(
        year=2026,
        month=8,
        plan_level="部门级",
        dept_alias_set={"质量部"},
    )

    created = result[0]
    assert result == [created, existing]
    assert created.target_audience == "质量部 质量全员"
    assert created.actual_time == "8月26日 09:00-10:00"
    assert created.sessions_snapshot == created.actual_time
    assert existing.actual_time == "人工填写"
    assert repo.create.await_count == 1
    assert session.flush.await_count == 3


def test_plan_tracking_month_and_session_format_helpers() -> None:
    assert plan_tracking_service._parse_month_int("01月") == 1
    assert plan_tracking_service._parse_month_int("13") is None
    assert plan_tracking_service._parse_month_int("无月份") is None
    assert (
        plan_tracking_service._format_session_time(
            SimpleNamespace(training_date=None, time_start="09:00", time_end="10:00")
        )
        == ""
    )
    assert (
        plan_tracking_service._format_session_time(
            SimpleNamespace(
                training_date=date(2026, 8, 26), time_start="09:00", time_end=None
            )
        )
        == "8月26日 09:00"
    )
