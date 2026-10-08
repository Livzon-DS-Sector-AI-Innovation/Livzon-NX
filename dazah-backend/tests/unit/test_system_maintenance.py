"""Admission, receipts and task drain against an explicitly isolated Redis."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core import database, jobs, maintenance, maintenance_middleware
from app.platform.scheduler.engine import SchedulerEngine
from app.platform.scheduler.registry import (
    ScheduleConfig,
    SchedulerRegistry,
    TaskDefinition,
)
from app.platform.system import operations

pytest_plugins = ("tests.maintenance_fixtures",)


async def test_drain_refuses_new_work_but_waits_for_admitted_parent_and_child(
    isolated_redis,
):
    async with maintenance.business_activity("request"):
        await maintenance.set_release_phase("draining")
        async with maintenance.business_activity("job"):
            assert await maintenance.active_work() == {"request": 1, "job": 1}
        assert await maintenance.active_work() == {"request": 1}
    assert await maintenance.active_work() == {}
    with pytest.raises(maintenance.MaintenanceActiveError):
        async with maintenance.business_activity("job"):
            pytest.fail("new job admitted")


async def test_cancelled_work_is_not_assumed_completed(isolated_redis):
    entered = asyncio.Event()

    async def work():
        async with maintenance.business_activity("job"):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(work())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await maintenance.active_work() == {"job": 1}


async def test_known_task_failure_finishes_drain_entry(isolated_redis):
    with pytest.raises(ValueError):
        async with maintenance.business_activity("job"):
            raise ValueError("fixture failure")
    assert await maintenance.active_work() == {}


async def test_database_session_is_counted_until_close(isolated_redis, monkeypatch):
    async with database.async_session_factory():
        assert await maintenance.active_work() == {"database-task": 1}
    assert await maintenance.active_work() == {}
    await maintenance.set_release_phase("draining")
    with pytest.raises(maintenance.MaintenanceActiveError):
        async with database.async_session_factory():
            pytest.fail("new background DB work admitted")


async def test_accepted_database_work_can_finish_nested_work_during_drain(
    isolated_redis,
):
    async with database.async_session_factory():
        await maintenance.set_release_phase("draining")
        async with database.async_session_factory():
            assert await maintenance.active_work() == {"database-task": 2}
    assert await maintenance.active_work() == {}


async def test_job_spawn_failure_leaves_no_false_active_task(
    isolated_redis, monkeypatch
):
    monkeypatch.setattr(jobs, "cache_set", AsyncMock())
    monkeypatch.setattr(jobs, "cache_delete", AsyncMock())

    def cannot_spawn(_coroutine):
        raise RuntimeError("fixture cannot spawn")

    monkeypatch.setattr(jobs.asyncio, "create_task", cannot_spawn)
    with pytest.raises(RuntimeError, match="cannot spawn"):
        await jobs.submit_job(AsyncMock())
    assert await maintenance.active_work() == {}


async def test_starting_allows_bootstrap_but_refuses_public_requests(isolated_redis):
    await maintenance.set_release_phase("starting")
    async with database.async_session_factory():
        assert (await maintenance.active_work())["database-task"] == 1
    with pytest.raises(maintenance.MaintenanceActiveError):
        async with maintenance.business_activity("request"):
            pytest.fail("public request admitted while starting")
    for kind in ("scheduler", "job", "event"):
        with pytest.raises(maintenance.MaintenanceActiveError):
            async with maintenance.business_activity(kind):
                pytest.fail("business work admitted before readiness")


def test_invalid_phase_rejected():
    with pytest.raises(ValueError):
        asyncio.run(maintenance.set_release_phase("ignored"))


async def test_corrupt_receipt_is_not_reported_as_missing_or_completed(
    isolated_redis, receipt_app
):
    identifier = str(uuid4())
    await isolated_redis.hset(
        maintenance_middleware.receipt_key("actor-a", identifier),
        "fixture",
        "invalid fixture json",
    )
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        result = await client.get(f"/api/v1/system/operations/{identifier}")
    assert result.status_code == 503
    assert "请勿重复提交" in result.text


@pytest.fixture
def receipt_app():
    app = FastAPI()
    app.include_router(operations.router, prefix="/api/v1/system")
    app.add_middleware(maintenance_middleware.MaintenanceMiddleware)
    app.state.writes = 0
    app.state.actor = "actor-a"
    app.state.wait = None

    @app.middleware("http")
    async def authenticate(request, call_next):
        request.state.audit_user_id = app.state.actor
        return await call_next(request)

    async def owner():
        if app.state.actor is None:
            raise HTTPException(401, "Login required")
        return SimpleNamespace(id=app.state.actor)

    app.dependency_overrides[operations.require_current_user] = owner

    @app.get("/api/v1/quality/records")
    async def records():
        return {"items": []}

    @app.post("/api/v1/quality/critical-write")
    async def write(request: Request):
        await request.json()
        app.state.writes += 1
        if app.state.wait:
            await app.state.wait.wait()
        return {"id": "business-fixture"}

    @app.post("/api/v1/quality/partial-failure")
    async def partial_failure():
        app.state.writes += 1
        raise HTTPException(502, "external acknowledgement unavailable")

    return app


async def test_confirmed_reads_can_refresh_without_poisoning_write_guard(
    isolated_redis, receipt_app
):
    identifier = str(uuid4())
    headers = {"X-Dazah-Operation-ID": identifier}
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        for _ in range(2):
            assert (
                await client.get("/api/v1/quality/records", headers=headers)
            ).status_code == 200
        result = await client.get(f"/api/v1/system/operations/{identifier}")
        assert [
            (record["method"], record["state"]) for record in result.json()["receipts"]
        ] == [("GET", "completed")]
        key = maintenance_middleware.receipt_key("actor-a", identifier)
        assert 0 < await isolated_redis.ttl(key) <= 300
        assert (
            await client.post(
                "/api/v1/quality/critical-write", json={}, headers=headers
            )
        ).status_code == 200
        assert 300 < await isolated_redis.ttl(key) <= 7 * 24 * 3600
        result = await client.get(f"/api/v1/system/operations/{identifier}")
        assert {record["method"] for record in result.json()["receipts"]} == {
            "GET",
            "POST",
        }
        assert (
            await client.post(
                "/api/v1/quality/critical-write", json={}, headers=headers
            )
        ).status_code == 409
        assert receipt_app.state.writes == 1


async def test_duplicate_write_runs_once_and_owner_can_query_metadata(
    isolated_redis, receipt_app
):
    identifier = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        args = {
            "json": {"input": "fixture"},
            "headers": {"X-Dazah-Operation-ID": identifier},
        }
        first = await client.post("/api/v1/quality/critical-write", **args)
        second = await client.post("/api/v1/quality/critical-write", **args)
        assert first.status_code == 200
        assert second.status_code == 409
        assert receipt_app.state.writes == 1
        result = await client.get(f"/api/v1/system/operations/{identifier}")
        assert result.status_code == 200
        assert result.json()["receipts"][0]["state"] == "completed"
        assert "input" not in result.text and "business-fixture" not in result.text
        receipt_app.state.actor = "actor-b"
        assert (
            await client.get(f"/api/v1/system/operations/{identifier}")
        ).status_code == 404
        receipt_app.state.actor = None
        assert (
            await client.get(f"/api/v1/system/operations/{identifier}")
        ).status_code == 401


async def test_inflight_write_stays_counted_and_concurrent_duplicate_is_refused(
    isolated_redis, receipt_app
):
    identifier = str(uuid4())
    receipt_app.state.wait = asyncio.Event()
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        args = {"json": {}, "headers": {"X-Dazah-Operation-ID": identifier}}
        task = asyncio.create_task(
            client.post("/api/v1/quality/critical-write", **args)
        )
        for _ in range(100):
            if receipt_app.state.writes:
                break
            await asyncio.sleep(0.01)
        assert await maintenance.active_work() == {"request": 1}
        assert (
            await client.post("/api/v1/quality/critical-write", **args)
        ).status_code == 409
        await maintenance.set_release_phase("draining")
        assert (
            await client.post("/api/v1/quality/critical-write", json={})
        ).status_code == 503
        assert receipt_app.state.writes == 1
        receipt_app.state.wait.set()
        assert (await task).status_code == 200
        assert await maintenance.active_work() == {}


async def test_partial_failure_retains_unknown_receipt_and_never_reexecutes(
    isolated_redis, receipt_app
):
    identifier = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        headers = {"X-Dazah-Operation-ID": identifier}
        assert (
            await client.post("/api/v1/quality/partial-failure", headers=headers)
        ).status_code == 502
        assert (
            await client.post("/api/v1/quality/partial-failure", headers=headers)
        ).status_code == 409
        result = await client.get(f"/api/v1/system/operations/{identifier}")
        assert result.json()["receipts"][0]["state"] == "unknown"
        assert receipt_app.state.writes == 1
        assert (
            await isolated_redis.ttl(
                maintenance_middleware.receipt_key("actor-a", identifier)
            )
            == -1
        )


async def test_redis_failure_refuses_execution_and_lookup_returns_503(
    monkeypatch, receipt_app
):
    from redis.exceptions import ConnectionError

    unavailable = SimpleNamespace(
        eval=AsyncMock(side_effect=ConnectionError()),
        hvals=AsyncMock(side_effect=ConnectionError()),
    )
    monkeypatch.setattr(maintenance, "redis_client", unavailable)
    monkeypatch.setattr(operations, "redis_client", unavailable)
    async with AsyncClient(
        transport=ASGITransport(app=receipt_app), base_url="http://fixture"
    ) as client:
        assert (
            await client.post("/api/v1/quality/critical-write", json={})
        ).status_code == 503
        assert receipt_app.state.writes == 0
        assert (
            await client.get(f"/api/v1/system/operations/{uuid4()}")
        ).status_code == 503


async def test_jobs_remain_in_drain_until_their_result_is_recorded(
    isolated_redis, monkeypatch
):
    monkeypatch.setattr(jobs, "cache_set", AsyncMock())
    monkeypatch.setattr(jobs, "cache_delete", AsyncMock())
    gate = asyncio.Event()
    await jobs.submit_job(lambda: gate.wait())
    await maintenance.set_release_phase("draining")
    assert await maintenance.active_work() == {"job": 1}
    with pytest.raises(maintenance.MaintenanceActiveError):
        await jobs.submit_job(lambda: gate.wait())
    gate.set()
    for _ in range(100):
        if not await maintenance.active_work():
            break
        await asyncio.sleep(0.01)
    assert await maintenance.active_work() == {}


async def test_scheduler_refuses_new_tasks_without_losing_due_time(isolated_redis):
    await maintenance.set_release_phase("draining")
    engine = SchedulerEngine(SchedulerRegistry())
    work = AsyncMock()
    task = TaskDefinition("fixture-task", ScheduleConfig(), work)
    await engine._maybe_run_task(task, SimpleNamespace())
    work.assert_not_awaited()
    assert task.name not in engine._last_run
    await maintenance.set_release_phase("normal")
    await engine._maybe_run_task(task, SimpleNamespace())
    work.assert_awaited_once()
    assert await maintenance.active_work() == {}
