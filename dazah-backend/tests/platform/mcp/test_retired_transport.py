"""Legacy MCP keys must not bypass the identity-aware Agent executor."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.platform.mcp import middleware, server


@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/tools", "/"])
async def test_legacy_transport_never_opens_database_or_invokes_tools(
    monkeypatch, path
):
    database = Mock(
        return_value=SimpleNamespace(
            commit=AsyncMock(),
            rollback=AsyncMock(),
            close=AsyncMock(),
        )
    )
    monkeypatch.setattr(middleware, "async_session_factory", database, raising=False)
    invoked = Mock()
    app = FastAPI()
    app.add_middleware(middleware.MCPAuthMiddleware, valid_keys={"synthetic-mcp-key"})

    @app.post("/{path:path}")
    async def old_tool(path: str):
        invoked()
        return {"changed": True}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            path,
            headers={"API-Key": "synthetic-mcp-key"},
            json={"jsonrpc": "2.0", "method": "tools/call", "id": 1},
        )
    assert response.status_code == 403
    invoked.assert_not_called()
    database.assert_not_called()


async def test_rejected_keys_are_not_logged(monkeypatch, caplog):
    app = FastAPI()
    app.add_middleware(middleware.MCPAuthMiddleware, valid_keys=set())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/mcp", headers={"API-Key": "sensitive-key-prefix-value"})
    assert "sensitiv" not in caplog.text


def test_server_factory_cannot_recreate_an_unprotected_http_app():
    with pytest.raises(RuntimeError, match="retired"):
        server.get_mcp_app()


async def test_main_application_does_not_mount_the_legacy_transport():
    from app.main import app

    assert all(getattr(route, "path", "") != "/mcp" for route in app.routes)
    async with AsyncClient(
        transport=ASGITransport(app=app.router), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp/",
            headers={"API-Key": "synthetic"},
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        )
    assert response.status_code == 404
