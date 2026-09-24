import uuid
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from starlette.requests import Request

from app.platform.identity import api, deps, service
from app.platform.identity.models import User
from app.platform.identity.schemas import LocalLoginRequest


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "scheme": "http",
        }
    )


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        name="审计用户",
        username="audit-user",
        role="user",
        status="active",
        auth_source="local",
        session_version=0,
        grant_version=0,
    )


@pytest.mark.asyncio
async def test_verified_user_is_exposed_to_request_audit(monkeypatch: Any) -> None:
    user = _user()

    async def get_by_id(self: Any, db: Any, user_id: str) -> User:
        assert user_id == str(user.id)
        return user

    monkeypatch.setattr(deps.UserRepository, "get_by_id", get_by_id)
    token = jwt.encode(
        {"sub": str(user.id), "session_version": 0}, "test-only-key", algorithm="HS256"
    )
    request = _request("/api/v1/identity/auth/session/logout")
    result = await deps.get_current_user(
        request,
        db=object(),
        settings=SimpleNamespace(SECRET_KEY="test-only-key"),
        auth_token=token,
    )
    assert result is user
    assert request.state.audit_user_id == user.id


@pytest.mark.asyncio
async def test_successful_local_login_identifies_actor(monkeypatch: Any) -> None:
    user = _user()

    async def allowed(_username: str) -> bool:
        return True

    async def authenticate(
        _db: Any, *, username: str, password: str
    ) -> tuple[User, str]:
        assert (username, password) == ("audit-user", "test-password")
        return user, "test-token"

    monkeypatch.setattr(
        "app.platform.identity.permission_middleware.check_local_account_rate_limit",
        allowed,
    )
    monkeypatch.setattr(service, "authenticate_local_user", authenticate)
    request = _request("/api/v1/identity/auth/local/login")
    response = await api.local_login(
        request,
        LocalLoginRequest(username="audit-user", password="test-password"),
        db=object(),
        settings=SimpleNamespace(
            effective_local_login_mode="enabled",
            is_production=False,
            JWT_EXPIRE_SECONDS=3600,
        ),
    )
    assert response.status_code == 200
    assert request.state.audit_user_id == user.id


@pytest.mark.asyncio
async def test_successful_sso_callback_identifies_actor(monkeypatch: Any) -> None:
    user = _user()

    async def callback(_db: Any, _code: str) -> tuple[User, str]:
        return user, "test-token"

    monkeypatch.setattr(
        service, "validate_state_token", lambda *_args: {"next": "/quality"}
    )
    monkeypatch.setattr(service, "handle_oauth_callback", callback)
    request = _request("/api/v1/identity/auth/callback")
    response = await api.auth_callback(
        request,
        code="test-code",
        state="test-state",
        error=None,
        feishu_oauth_state="test-state",
        db=object(),
        settings=SimpleNamespace(FRONTEND_URL="http://test", JWT_EXPIRE_SECONDS=3600),
    )
    assert response.status_code == 302
    assert request.state.audit_user_id == user.id
