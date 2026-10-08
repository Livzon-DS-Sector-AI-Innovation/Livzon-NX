import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.core import maintenance
from app.modules.research.pilot_workflow import engine

pytest_plugins = ("tests.maintenance_fixtures",)


async def test_approved_workflow_step_blocks_release_until_background_execution_ends(
    isolated_redis, monkeypatch
):
    gate = asyncio.Event()
    workflow_id = uuid4()
    workflow = SimpleNamespace(status="waiting_approval")
    first = SimpleNamespace(
        status="waiting_approval",
        output_data={"fixture": True},
        step_code="extract",
        step_order=1,
    )
    second = SimpleNamespace(status="pending", step_order=2, step_name="scale")
    session = SimpleNamespace(
        commit=AsyncMock(),
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: workflow),
                SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: [first, second])
                ),
            ]
        ),
    )

    @asynccontextmanager
    async def factory():
        yield session

    async def execute(_identifier, _index):
        await gate.wait()

    monkeypatch.setattr(engine, "async_session_factory", factory)
    monkeypatch.setattr(engine, "_execute_next_step_async", execute)
    async with maintenance.business_activity("request"):
        result = await engine.approve_step(workflow_id)
    assert result["status"] == "running"
    assert first.status == "completed"
    assert second.status == "running"
    session.commit.assert_awaited_once()
    await maintenance.set_release_phase("draining")
    assert await maintenance.active_work() == {"job": 1}
    gate.set()
    for _ in range(100):
        if not await maintenance.active_work():
            break
        await asyncio.sleep(0.01)
    assert await maintenance.active_work() == {}
