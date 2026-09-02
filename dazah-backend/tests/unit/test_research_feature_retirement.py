"""Removed optimization routes must not affect the remaining research API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.research import api


@pytest.mark.asyncio
async def test_retired_optimization_routes_and_retained_project_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/research")
    app.dependency_overrides[get_db] = lambda: None
    list_projects = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(api.service, "get_projects", list_projects)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("optimize", "generate-scope"):
            response = await client.post(f"/api/v1/research/edbo/{path}", json={})
            assert response.status_code == 404
        response = await client.get("/api/v1/research/projects")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == 0
    list_projects.assert_awaited_once()
    paths = app.openapi()["paths"]
    assert "/api/v1/research/ich/analyze" in paths
    assert not any("/edbo/" in path for path in paths)
