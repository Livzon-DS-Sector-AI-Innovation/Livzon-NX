"""Retiring CPV HTTP entry points must preserve the stored data models."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.quality.api import router


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/cpv/products"),
        ("POST", "/cpv/products"),
        ("POST", "/cpv/import/preview"),
        ("POST", "/cpv/import/confirm"),
    ],
)
async def test_retired_cpv_routes_are_unavailable(method, path):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/quality")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, "/api/v1/quality" + path)
    assert response.status_code == 404
    assert not any(
        getattr(route, "path", "").startswith("/cpv/") for route in router.routes
    )
