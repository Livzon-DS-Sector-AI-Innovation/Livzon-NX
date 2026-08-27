"""Failure-isolation tests for the safety scheduled-task loop."""

from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.safety import scheduler

SimpleNamespace: Any = _SimpleNamespace


def _task() -> Any:
    return SimpleNamespace(
        id=uuid4(),
        name="每日安全提醒",
        data_sources=[
            {"key": "hazards", "enabled": True},
            {"key": "disabled", "enabled": False},
            {"key": "missing", "enabled": True},
        ],
        card_template="{{ hazards }}",
        header_color="red",
        feishu_chat_id="chat",
        cron_expression="0 8 * * *",
    )


def test_compute_next_run_preserves_timezone() -> None:
    base = datetime(2026, 1, 1, 7, 30, tzinfo=UTC)
    result = scheduler.compute_next_run("0 8 * * *", base)
    assert result.hour == 8
    assert result.tzinfo is not None


@pytest.mark.asyncio
async def test_execute_single_task_records_success(monkeypatch: Any) -> None:
    task = _task()
    repo: Any = SimpleNamespace(
        create_task_log=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        update_task_log=AsyncMock(),
        update_scheduled_task=AsyncMock(),
    )
    monkeypatch.setattr(
        "app.modules.safety.card_builder.fetch_data_sources",
        AsyncMock(return_value={"hazards": "2项隐患", "extra": "ignored"}),
    )
    monkeypatch.setattr(
        "app.modules.safety.card_builder.render_template",
        lambda template, variables: variables["hazards"],
    )
    monkeypatch.setattr(
        "app.modules.safety.card_builder.build_card_json",
        AsyncMock(return_value={"card": True}),
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_group_card",
        AsyncMock(return_value="message-id"),
    )

    await scheduler.execute_single_task(task, repo)

    success_log = repo.update_task_log.await_args.args[1]
    assert success_log["status"] == "success"
    assert success_log["data_snapshot"]["hazards"] == "2项隐患"
    assert success_log["feishu_msg_id"] == "message-id"
    success_task = repo.update_scheduled_task.await_args.args[1]
    assert success_task["last_run_status"] == "success"
    assert success_task["last_error"] is None


@pytest.mark.asyncio
async def test_execute_single_task_contains_fetch_and_status_update_failures(
    monkeypatch: Any,
) -> None:
    task = _task()
    repo: Any = SimpleNamespace(
        create_task_log=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        update_task_log=AsyncMock(side_effect=RuntimeError("log unavailable")),
        update_scheduled_task=AsyncMock(side_effect=RuntimeError("task unavailable")),
    )
    monkeypatch.setattr(
        "app.modules.safety.card_builder.fetch_data_sources",
        AsyncMock(side_effect=RuntimeError("Feishu timeout")),
    )

    await scheduler.execute_single_task(task, repo)

    repo.update_task_log.assert_awaited_once()
    failure_log = repo.update_task_log.await_args.args[1]
    assert failure_log["status"] == "failure"
    assert failure_log["error_message"] == "Feishu timeout"
    repo.update_scheduled_task.assert_awaited_once()
    failure_task = repo.update_scheduled_task.await_args.args[1]
    assert failure_task["last_run_status"] == "failure"


@pytest.mark.asyncio
async def test_scheduled_task_loop_commits_due_tasks_and_stops(
    monkeypatch: Any,
) -> None:
    scheduler.stop_scheduled_task_flag.clear()
    task = _task()
    repo: Any = SimpleNamespace(get_due_scheduled_tasks=AsyncMock(return_value=[task]))
    session: Any = SimpleNamespace(commit=AsyncMock())

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return session

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        SessionContext,
    )
    monkeypatch.setattr(
        "app.modules.safety.repository.SafetyRepository",
        lambda _session: repo,
    )
    execute: Any = AsyncMock()
    monkeypatch.setattr(scheduler, "execute_single_task", execute)

    async def fake_wait_for(awaitable: Any, *, timeout: Any) -> Any:
        awaitable.close()
        scheduler.stop_scheduled_task_flag.set()
        raise TimeoutError

    monkeypatch.setattr(scheduler.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    await scheduler.scheduled_task_loop()

    execute.assert_awaited_once_with(task, repo)
    session.commit.assert_awaited_once()
    scheduler.stop_scheduled_task_flag.clear()


@pytest.mark.asyncio
async def test_scheduled_task_loop_contains_database_failure(
    monkeypatch: Any,
) -> None:
    scheduler.stop_scheduled_task_flag.clear()

    class FailingContext:
        async def __aenter__(self: Any) -> Any:
            raise RuntimeError("database unavailable")

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        FailingContext,
    )

    async def fake_wait_for(awaitable: Any, *, timeout: Any) -> Any:
        awaitable.close()
        scheduler.stop_scheduled_task_flag.set()

    monkeypatch.setattr(scheduler.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    await scheduler.scheduled_task_loop()
    scheduler.stop_scheduled_task_flag.clear()
