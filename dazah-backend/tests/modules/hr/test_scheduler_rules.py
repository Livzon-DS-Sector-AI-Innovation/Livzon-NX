from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core import redis
from app.modules.hr import (
    contract_api,
    mail_fetcher,
    repository,
    resume_watcher,
    scheduler,
)

SimpleNamespace: Any = _SimpleNamespace


class _Scalars:
    def __init__(self: Any, values: Any) -> None:
        self.values = values

    def all(self: Any) -> Any:
        return self.values


class _Result:
    def __init__(self: Any, values: Any) -> None:
        self.values = values

    def scalars(self: Any) -> Any:
        return _Scalars(self.values)


@pytest.mark.anyio
async def test_resume_and_mail_scanners_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resume_watcher, "scan_watched_folder", AsyncMock(return_value={"new_files": 1})
    )
    monkeypatch.setattr(
        mail_fetcher, "fetch_resumes_from_mail", AsyncMock(return_value={"fetched": 2})
    )
    resume = scheduler.ResumeFolderScanner()
    mail = scheduler.MailFetchScanner()
    assert await resume.find_due(None) == [None]
    assert await mail.find_due(None) == [None]
    await resume.execute_one(None, None)
    await mail.execute_one(None, None)


@pytest.mark.anyio
async def test_offboarding_execute_sends_deduplicated_cards_and_records_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: Any = SimpleNamespace(
        id=uuid4(),
        name="张三",
        employee_number="E001",
        department="质量部",
        offboarding_date=date(2026, 8, 31),
        offboarding_type="辞职",
        reminder_sent=False,
        reminder_sent_at=None,
    )
    send: Any = AsyncMock(side_effect=[None, RuntimeError("send failed")])
    monkeypatch.setattr(scheduler.feishu_notification, "send_user_card", send)  # type: ignore[attr-defined]
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value='["old"]'))
    cache_set: Any = AsyncMock()
    monkeypatch.setattr(redis, "cache_set", cache_set)
    await scheduler.OffboardingReminderGenerator().execute_one(
        SimpleNamespace(),
        {
            "records": [record],
            "recipient_open_ids": ["ou1", "ou1", "ou2"],
            "message_template": "{姓名}/{工号}/{部门}/{离职日期}/{离职类型}",
            "today": "2026-08-20",
        },
    )
    assert send.await_count == 2
    assert record.reminder_sent is True
    assert record.reminder_sent_at is not None
    cache_set.assert_awaited_once()

    send.reset_mock()
    await scheduler.OffboardingReminderGenerator().execute_one(
        SimpleNamespace(),
        {
            "records": [record],
            "recipient_open_ids": ["ou1"],
            "message_template": "",
            "today": "2026-08-20",
        },
    )
    assert "离职手续未办结" in send.await_args.kwargs["content"]


@pytest.mark.anyio
async def test_offboarding_execute_skips_without_recipients() -> None:
    await scheduler.OffboardingReminderGenerator().execute_one(
        SimpleNamespace(),
        {
            "records": [],
            "recipient_open_ids": [],
            "message_template": "",
            "today": "2026-08-20",
        },
    )


@pytest.mark.anyio
async def test_contract_sign_execute_resolves_clerks_sends_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config: Any = SimpleNamespace(
        sign_clerk_open_ids=["clerk"], recipient_open_ids=["hr"]
    )
    session: Any = SimpleNamespace(execute=AsyncMock(return_value=_Result([config])))
    item: Any = SimpleNamespace(
        id=uuid4(),
        employee_number="E001",
        name="张三",
        dept_level1="质量部",
        dept_level2="QA",
        supervisor_approved_at=datetime(2026, 8, 1),
        sign_reminded_at=None,
    )
    monkeypatch.setattr(
        contract_api,
        "_resolve_contract_clerk_ids",
        AsyncMock(return_value=["ou1", "ou2"]),
    )
    send: Any = AsyncMock(side_effect=[None, RuntimeError("send failed")])
    monkeypatch.setattr(scheduler.feishu_notification, "send_user_card", send)  # type: ignore[attr-defined]
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(redis, "cache_set", AsyncMock())
    await scheduler.ContractSignReminderGenerator().execute_one(session, item)
    assert send.await_count == 2
    assert item.sign_reminded_at is not None

    contract_api._resolve_contract_clerk_ids.return_value = []  # type: ignore[attr-defined]
    item.sign_reminded_at = None
    await scheduler.ContractSignReminderGenerator().execute_one(session, item)
    assert item.sign_reminded_at is None


@pytest.mark.anyio
async def test_contract_expiry_execute_limits_summary_and_updates_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employees = [
        {
            "employee_id": str(uuid4()),
            "name": f"员工{i}",
            "department": "质量部",
            "contract_sequence": 2,
            "contract_end_date": "2026-09-01",
        }
        for i in range(21)
    ]
    send: Any = AsyncMock(side_effect=[None, RuntimeError("send failed")])
    monkeypatch.setattr(scheduler.feishu_notification, "send_user_card", send)  # type: ignore[attr-defined]
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    cache_set: Any = AsyncMock()
    monkeypatch.setattr(redis, "cache_set", cache_set)
    await scheduler.ContractExpiryReminderGenerator().execute_one(
        SimpleNamespace(),
        {
            "employees": employees,
            "recipient_open_ids": ["ou1", "ou1", "ou2"],
            "today": "2026-08-20",
        },
    )
    assert send.await_count == 2
    assert "共 21 人" in send.await_args_list[0].kwargs["content"]
    cache_set.assert_awaited_once()


@pytest.mark.anyio
async def test_offboarding_find_due_applies_trigger_and_daily_dedup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config: Any = SimpleNamespace(
        is_enabled=True,
        trigger_hour=datetime.now().hour,
        notify_hours=24,
        message_template="模板",
        recipient_open_ids=["ou1", "ou1", "ou2"],
    )
    record: Any = SimpleNamespace(id=uuid4())
    session: Any = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result([config]), _Result([record])])
    )
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    due = await scheduler.OffboardingReminderGenerator().find_due(session)
    assert due[0]["records"] == [record]
    assert due[0]["recipient_open_ids"] == ["ou1", "ou2"]

    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value="done"))
    session.execute = AsyncMock(return_value=_Result([config]))
    assert await scheduler.OffboardingReminderGenerator().find_due(session) == []


@pytest.mark.anyio
async def test_contract_sign_find_due_filters_already_notified_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config: Any = SimpleNamespace(sign_reminder_days=3)
    first: Any = SimpleNamespace(id=uuid4())
    second: Any = SimpleNamespace(id=uuid4())
    session: Any = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result([config]), _Result([first, second])])
    )
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=f'["{first.id}"]'))
    due = await scheduler.ContractSignReminderGenerator().find_due(session)
    assert due == [second]

    session.execute = AsyncMock(return_value=_Result([]))
    assert await scheduler.ContractSignReminderGenerator().find_due(session) == []


@pytest.mark.anyio
async def test_contract_expiry_find_due_collects_unique_employees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config: Any = SimpleNamespace(
        is_enabled=True,
        trigger_frequency="daily",
        trigger_day=1,
        trigger_hour=datetime.now().hour,
        reminder_days=[30, 60, 30],
        recipient_open_ids=["ou1", "ou1", "ou2"],
    )
    employee = {
        "employee_id": "e1",
        "name": "张三",
        "contract_end_date": "2026-09-01",
    }
    session: Any = SimpleNamespace(execute=AsyncMock(return_value=_Result([config])))
    monkeypatch.setattr(redis, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(
        repository.EmployeeRepository,
        "list_contract_expiring",
        AsyncMock(return_value=([employee], 1)),
    )
    due = await scheduler.ContractExpiryReminderGenerator().find_due(session)
    assert due[0]["employees"] == [employee]
    assert due[0]["recipient_open_ids"] == ["ou1", "ou2"]
