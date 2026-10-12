import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.modules.agent.scheduled import create_access_scope_sync_engine
from app.platform.scheduler import engine as engine_module
from app.platform.scheduler.engine import SchedulerEngine
from app.platform.scheduler.registry import SchedulerRegistry, TaskGenerator


@pytest.mark.asyncio
async def test_permission_sync_advances_while_business_scheduler_is_blocked(
    monkeypatch,
):
    business_started = asyncio.Event()
    release_business = asyncio.Event()
    scope_processed = asyncio.Event()

    class SlowBusinessGenerator(TaskGenerator):
        name = "slow_business_sync"

        async def find_due(self, session):
            business_started.set()
            await release_business.wait()
            return []

        async def execute_one(self, session, item):
            raise AssertionError("No business work is due")

    @asynccontextmanager
    async def admission(kind):
        yield

    @asynccontextmanager
    async def session_factory():
        yield AsyncMock()

    async def process_scope(self, session, event):
        scope_processed.set()

    from app.modules.agent.scheduled import AgentAccessScopeSyncGenerator

    monkeypatch.setattr(engine_module, "business_activity", admission)
    monkeypatch.setattr(engine_module, "async_session_factory", session_factory)
    monkeypatch.setattr(
        AgentAccessScopeSyncGenerator, "find_due", AsyncMock(return_value=[object()])
    )
    monkeypatch.setattr(AgentAccessScopeSyncGenerator, "execute_one", process_scope)
    general_registry = SchedulerRegistry()
    general_registry.register_generator(SlowBusinessGenerator())
    general_engine = SchedulerEngine(general_registry)
    scope_engine = create_access_scope_sync_engine()
    business_task = asyncio.create_task(general_engine.run())
    scope_task = None
    try:
        await asyncio.wait_for(business_started.wait(), timeout=2)
        scope_task = asyncio.create_task(scope_engine.run())
        await asyncio.wait_for(scope_processed.wait(), timeout=2)
        assert not release_business.is_set()
        assert not business_task.done()
    finally:
        general_engine.stop()
        scope_engine.stop()
        release_business.set()
        tasks = [business_task] + ([scope_task] if scope_task else [])
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
    assert all(task.done() for task in tasks)
