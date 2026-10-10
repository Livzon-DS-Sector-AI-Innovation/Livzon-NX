import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import maintenance
from app.core.maintenance_middleware import MaintenanceMiddleware
from app.platform.identity import api, repository
from app.platform.integrations.feishu import sync

pytest_plugins = ("tests.maintenance_fixtures",)


@pytest.mark.parametrize(
    "action,worker,setting",
    [
        ("departments", "sync_departments", "FEISHU_SYNC_ROOT_DEPT_ID"),
        ("members", "sync_members", "FEISHU_SYNC_MEMBER_DEPT_ID"),
    ],
)
async def test_directory_job_registered_before_request_ends_and_drains_external_wait(
    isolated_redis, monkeypatch, action, worker, setting
):
    gate = asyncio.Event()
    finished = asyncio.Event()

    async def synchronize(*args, **kwargs):
        await gate.wait()
        finished.set()

    monkeypatch.setattr(
        repository.FeishuConfigRepository, "get_active", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(sync, worker, synchronize)
    app = FastAPI()
    app.include_router(api.sync_router, prefix="/api/v1/identity")
    app.add_middleware(MaintenanceMiddleware)
    app.dependency_overrides[api.get_db] = lambda: None
    app.dependency_overrides[api.get_settings] = lambda: SimpleNamespace(
        **{setting: "fixture-root"}
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        response = await client.post(f"/api/v1/identity/sync/{action}")
        assert response.json()["code"] == 200
        await maintenance.set_release_phase("draining")
        assert (await client.post(f"/api/v1/identity/sync/{action}")).status_code == 503
    assert response.status_code == 200
    assert await maintenance.active_work() == {"job": 1}
    assert not finished.is_set()
    gate.set()
    for _ in range(100):
        if not await maintenance.active_work():
            break
        await asyncio.sleep(0.01)
    assert finished.is_set()
    assert await maintenance.active_work() == {}
