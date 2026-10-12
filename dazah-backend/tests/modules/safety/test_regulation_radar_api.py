"""法规雷达端点的路由测试（扫描触发、批次查询、通知测试发送）。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.safety.api import knowledge as api
from app.modules.safety.models import RegulationRadarRun


@pytest.fixture
def radar_app(db_session: AsyncSession) -> FastAPI:
    application = FastAPI()
    application.include_router(api.knowledge_router, prefix="/api/v1/safety")

    async def _override_db():
        yield db_session

    application.dependency_overrides[get_db] = _override_db
    application.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    return application


@pytest.fixture
def radar_client(radar_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=radar_app), base_url="http://test")


@pytest.mark.anyio
async def test_run_endpoint_forwards_dry_run_and_trigger(
    radar_client: AsyncClient, monkeypatch
) -> None:
    fake = AsyncMock(return_value={"status": "success", "new_count": 1})
    monkeypatch.setattr(api.regulation_radar, "run_radar", fake)

    resp = await radar_client.post(
        "/api/v1/safety/knowledge-articles/radar/run?dry_run=true"
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["new_count"] == 1
    assert fake.await_args.kwargs == {"dry_run": True, "trigger": "manual"}


@pytest.mark.anyio
async def test_runs_list_and_detail(
    radar_client: AsyncClient, db_session: AsyncSession
) -> None:
    row = RegulationRadarRun(
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status="success",
        trigger="schedule",
        dry_run=False,
        sites_total=3,
        sites_failed=0,
        found_count=5,
        new_count=2,
        revised_count=1,
    )
    db_session.add(row)
    await db_session.commit()

    try:
        listing = await radar_client.get(
            "/api/v1/safety/knowledge-articles/radar/runs?limit=5"
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body["meta"]["total"] >= 1
        assert any(item["id"] == str(row.id) for item in body["data"])

        detail = await radar_client.get(
            f"/api/v1/safety/knowledge-articles/radar/runs/{row.id}"
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["status"] == "success"

        missing = await radar_client.get(
            f"/api/v1/safety/knowledge-articles/radar/runs/{uuid4()}"
        )
        assert missing.json()["code"] == 404
        assert "不存在" in missing.json()["message"]
    finally:
        await db_session.rollback()
        await db_session.delete(row)
        await db_session.commit()


@pytest.mark.anyio
async def test_notify_test_endpoint_returns_send_result(
    radar_client: AsyncClient, monkeypatch
) -> None:
    fake = AsyncMock(return_value={"sent": 2, "errors": []})
    monkeypatch.setattr(api.regulation_radar, "send_test_notification", fake)

    resp = await radar_client.post(
        "/api/v1/safety/knowledge-articles/radar/notify/test"
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["sent"] == 2
    fake.assert_awaited_once()
