"""Unit tests for the shared scheduler primitives and execution engine."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest

from app.platform.scheduler import engine as engine_module
from app.platform.scheduler.engine import SchedulerEngine
from app.platform.scheduler.registry import (
    ScheduleConfig,
    SchedulerRegistry,
    ScheduleStrategy,
    TaskDefinition,
    TaskGenerator,
    get_action_handler,
    register_action_handler,
)
from app.platform.scheduler.strategies import is_due

SimpleNamespace: Any = _SimpleNamespace


async def _noop() -> None:
    return None


class FakeGenerator(TaskGenerator):
    name = "fake-generator"

    def __init__(self: Any, items: list[str] | None = None) -> None:
        self.items = items or []
        self.executed: list[str] = []

    async def find_due(self: Any, _session: Any) -> Any:
        return self.items

    async def execute_one(self: Any, _session: Any, item: Any) -> None:
        self.executed.append(item)


def test_registry_rejects_duplicates_and_returns_copies() -> None:
    registry = SchedulerRegistry()
    task = TaskDefinition("task", ScheduleConfig(), _noop)
    generator: Any = FakeGenerator()
    registry.register_task(task)
    registry.register_generator(generator)

    assert registry.tasks == {"task": task}
    assert registry.generators == {"fake-generator": generator}
    registry.tasks.clear()
    assert "task" in registry.tasks

    with pytest.raises(ValueError, match="Duplicate task"):
        registry.register_task(task)
    with pytest.raises(ValueError, match="Duplicate generator"):
        registry.register_generator(generator)

    generator.name = ""
    with pytest.raises(ValueError, match="name must be set"):
        SchedulerRegistry().register_generator(generator)


def test_action_handler_registry() -> None:
    action_type = "ci.scheduler.test"
    register_action_handler(action_type, _noop)
    assert get_action_handler(action_type) is _noop
    assert get_action_handler("missing") is None
    with pytest.raises(ValueError, match="already registered"):
        register_action_handler(action_type, _noop)


@pytest.mark.parametrize(
    ("schedule", "last_run", "now", "expected"),
    [
        (
            ScheduleConfig(interval_seconds=60),
            None,
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
        (
            ScheduleConfig(interval_seconds=60),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 59, tzinfo=UTC),
            False,
        ),
        (
            ScheduleConfig(strategy=ScheduleStrategy.CRON, expression="0 * * * *"),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            True,
        ),
        (
            ScheduleConfig(strategy=ScheduleStrategy.CRON, expression=""),
            None,
            datetime(2026, 1, 1, tzinfo=UTC),
            False,
        ),
        (
            ScheduleConfig(strategy=ScheduleStrategy.FIXED_TIME, time_of_day="09:00"),
            None,
            datetime(2026, 1, 1, 10, tzinfo=UTC),
            True,
        ),
        (
            ScheduleConfig(strategy=ScheduleStrategy.FIXED_TIME, time_of_day="09:00"),
            datetime(2026, 1, 1, 8, tzinfo=UTC),
            datetime(2026, 1, 1, 8, 30, tzinfo=UTC),
            False,
        ),
        (
            ScheduleConfig(strategy=ScheduleStrategy.FIXED_TIME, time_of_day="09:00"),
            datetime(2025, 12, 31, 10, tzinfo=UTC),
            datetime(2026, 1, 1, 10, tzinfo=UTC),
            True,
        ),
    ],
)
def test_schedule_strategies(
    schedule: Any, last_run: Any, now: Any, expected: Any
) -> None:
    assert is_due(schedule, last_run, now) is expected


def test_engine_tick_interval_validation_and_stop() -> None:
    engine = SchedulerEngine(SchedulerRegistry())
    engine.tick_interval = 0.25
    assert engine.tick_interval == 0.25
    with pytest.raises(ValueError, match="positive"):
        engine.tick_interval = 0
    engine.stop()
    assert engine._stop_flag.is_set()


@pytest.mark.asyncio
async def test_engine_runs_due_task_and_honors_switches(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def record() -> None:
        calls.append("ran")

    engine = SchedulerEngine(SchedulerRegistry())
    task = TaskDefinition("enabled", ScheduleConfig(), record)
    await engine._maybe_run_task(task, SimpleNamespace())
    assert calls == ["ran"]
    assert "enabled" in engine._last_run

    disabled = TaskDefinition("disabled", ScheduleConfig(), record, enabled=False)
    toggled = TaskDefinition(
        "toggled",
        ScheduleConfig(),
        record,
        settings_toggle_key="FEATURE_ENABLED",
    )
    await engine._maybe_run_task(disabled, SimpleNamespace())
    await engine._maybe_run_task(toggled, SimpleNamespace(FEATURE_ENABLED=False))
    assert calls == ["ran"]

    monkeypatch.setattr(engine_module, "is_due", lambda *_args: False)
    await engine._maybe_run_task(
        TaskDefinition("not-due", ScheduleConfig(), record),
        SimpleNamespace(),
    )
    assert calls == ["ran"]


@pytest.mark.asyncio
async def test_engine_contains_task_failures() -> None:
    async def fail() -> None:
        raise RuntimeError("boom")

    engine = SchedulerEngine(SchedulerRegistry())
    await engine._maybe_run_task(
        TaskDefinition("failure", ScheduleConfig(), fail),
        SimpleNamespace(),
    )
    assert "failure" in engine._last_run


@pytest.mark.asyncio
async def test_engine_processes_generator_items_and_commits(monkeypatch: Any) -> None:
    class Session:
        committed = False

        async def commit(self: Any) -> None:
            self.committed = True

    session = Session()

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return session

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(engine_module, "async_session_factory", SessionContext)
    generator: Any = FakeGenerator(["a", "b"])
    engine = SchedulerEngine(SchedulerRegistry())
    await engine._maybe_run_generator(generator, SimpleNamespace())

    assert generator.executed == ["a", "b"]
    assert session.committed is True


@pytest.mark.asyncio
async def test_engine_generator_switches_and_item_failure(monkeypatch: Any) -> None:
    class FailingGenerator(FakeGenerator):
        async def execute_one(self: Any, _session: Any, item: Any) -> None:
            if item == "bad":
                raise RuntimeError("bad item")
            await super().execute_one(_session, item)

    class Session:
        async def commit(self: Any) -> None:
            return None

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return Session()

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(engine_module, "async_session_factory", SessionContext)
    generator = FailingGenerator(["bad", "good"])
    engine = SchedulerEngine(SchedulerRegistry())
    await engine._maybe_run_generator(generator, SimpleNamespace())
    assert generator.executed == ["good"]

    generator.enabled = False
    await engine._maybe_run_generator(generator, SimpleNamespace())
    generator.enabled = True
    generator.settings_toggle_key = "RUN_GENERATOR"
    await engine._maybe_run_generator(generator, SimpleNamespace(RUN_GENERATOR=False))
    assert generator.executed == ["good"]


@pytest.mark.asyncio
async def test_engine_run_completes_one_tick_and_stops(monkeypatch: Any) -> None:
    engine = SchedulerEngine(SchedulerRegistry())

    async def stop_on_wait(awaitable: Any, *, timeout: Any) -> Any:
        awaitable.close()
        engine.stop()

    monkeypatch.setattr(engine_module.asyncio, "wait_for", stop_on_wait)  # type: ignore[attr-defined]
    await engine.run()


@pytest.mark.asyncio
async def test_engine_contains_task_timeout(monkeypatch: Any) -> None:
    async def never_finishes() -> None:
        return None

    async def timeout(awaitable: Any, *, timeout: Any) -> Any:
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(engine_module.asyncio, "wait_for", timeout)  # type: ignore[attr-defined]
    engine = SchedulerEngine(SchedulerRegistry())
    await engine._maybe_run_task(
        TaskDefinition("timeout", ScheduleConfig(), never_finishes),
        SimpleNamespace(),
    )
    assert "timeout" in engine._last_run


@pytest.mark.asyncio
async def test_engine_contains_generator_find_and_commit_failures(
    monkeypatch: Any,
) -> None:
    class Session:
        async def commit(self: Any) -> None:
            raise RuntimeError("commit failed")

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return Session()

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(engine_module, "async_session_factory", SessionContext)
    engine = SchedulerEngine(SchedulerRegistry())

    class FindFailure(FakeGenerator):
        name = "find-failure"

        async def find_due(self: Any, _session: Any) -> Any:
            raise RuntimeError("query failed")

    await engine._maybe_run_generator(FindFailure(), SimpleNamespace())

    commit_failure: Any = FakeGenerator(["item"])
    commit_failure.name = "commit-failure"
    await engine._maybe_run_generator(commit_failure, SimpleNamespace())
    assert commit_failure.executed == ["item"]


@pytest.mark.asyncio
async def test_engine_contains_generator_timeouts(monkeypatch: Any) -> None:
    class Session:
        async def commit(self: Any) -> None:
            return None

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return Session()

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(engine_module, "async_session_factory", SessionContext)
    calls = 0

    async def timeout_find_then_first_item(awaitable: Any, *, timeout: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls in {1, 3}:
            awaitable.close()
            raise TimeoutError
        return await awaitable

    monkeypatch.setattr(
        engine_module.asyncio,  # type: ignore[attr-defined]
        "wait_for",
        timeout_find_then_first_item,
    )
    engine = SchedulerEngine(SchedulerRegistry())
    find_timeout: Any = FakeGenerator(["unused"])
    find_timeout.name = "find-timeout"
    await engine._maybe_run_generator(find_timeout, SimpleNamespace())

    item_timeout: Any = FakeGenerator(["slow", "good"])
    item_timeout.name = "item-timeout"
    await engine._maybe_run_generator(item_timeout, SimpleNamespace())
    assert item_timeout.executed == ["good"]


def test_interval_boundary() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert is_due(
        ScheduleConfig(interval_seconds=60),
        now - timedelta(seconds=60),
        now,
    )
