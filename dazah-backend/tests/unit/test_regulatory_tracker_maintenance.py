import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import maintenance
from app.core.maintenance_middleware import MaintenanceMiddleware
from app.modules.regulatory_tracker.api import routes

pytest_plugins = ("tests.maintenance_fixtures",)


async def test_crawler_is_drained_and_new_manual_sync_is_rejected(
    isolated_redis, monkeypatch
):
    gate = asyncio.Event()

    async def crawl(_days):
        await gate.wait()

    monkeypatch.setattr(routes, "_run_sync_background", crawl)
    monkeypatch.setattr(routes, "_sync_task_state", {"status": "idle"})
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.add_middleware(MaintenanceMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        response = await client.post("/api/v1/regulatory-documents/sync?recentDays=2")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "started"
        await maintenance.set_release_phase("draining")
        assert await maintenance.active_work() == {"job": 1}
        assert (
            await client.post("/api/v1/regulatory-documents/sync?recentDays=2")
        ).status_code == 503
        gate.set()
        for _ in range(100):
            if not await maintenance.active_work():
                break
            await asyncio.sleep(0.01)
        assert await maintenance.active_work() == {}
