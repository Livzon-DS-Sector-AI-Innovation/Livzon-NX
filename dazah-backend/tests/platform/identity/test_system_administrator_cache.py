from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.platform.identity import permission_cache
from app.platform.identity import permission_middleware as middleware
from app.platform.identity.repository import UserRepository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "status", "cached", "include_open_id", "expected"),
    [
        ("admin", "active", [], True, 200),
        ("user", "active", ["*"], True, 403),
        ("admin", "disabled", ["*"], True, 401),
        ("admin", "active", [], False, 200),
    ],
)
async def test_identity_precedes_stale_wildcard_cache(
    monkeypatch, role, status, cached, include_open_id, expected
):
    user = SimpleNamespace(id=uuid4(), role=role, status=status)
    settings = SimpleNamespace(
        DEV_BYPASS_AUTH=False,
        SECRET_KEY="test-only-signing-key-32-characters",
        effective_module_access_mode="roles",
    )
    payload = {"sub": str(user.id)}
    if include_open_id:
        payload["open_id"] = "test-open-id"
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/hr/test",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "app": SimpleNamespace(dependency_overrides={}),
        }
    )
    monkeypatch.setattr(middleware, "get_settings", lambda: settings)
    monkeypatch.setattr(middleware, "_matches_registered_route", lambda _: True)
    monkeypatch.setattr(middleware, "async_session_factory", lambda: AsyncMock())
    monkeypatch.setattr(UserRepository, "get_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        permission_cache, "get_cached_permissions", AsyncMock(return_value=cached)
    )
    monkeypatch.setattr(permission_cache, "set_cached_permissions", AsyncMock())
    resolve = AsyncMock(return_value=[])
    monkeypatch.setattr(middleware, "resolve_user_permissions", resolve)
    monkeypatch.setattr(
        middleware.PagePermissionRepository, "get_rollout", AsyncMock(return_value=None)
    )
    instance = middleware.PermissionMiddleware(None)
    monkeypatch.setattr(
        instance, "_maybe_renew", AsyncMock(return_value=Response(status_code=200))
    )
    response = await instance.dispatch(request, AsyncMock())
    assert response.status_code == expected
    if role == "user":
        resolve.assert_awaited_once()
