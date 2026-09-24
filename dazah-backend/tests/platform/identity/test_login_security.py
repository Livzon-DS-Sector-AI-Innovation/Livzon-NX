from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User
from app.platform.identity.service import generate_jwt, verify_password


@pytest.mark.anyio
async def test_logout_revokes_existing_jwt(db_session: AsyncSession) -> None:
    user = User(
        name="会话撤销测试",
        username=f"revoke-{uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
        session_version=0,
    )
    db_session.add(user)
    await db_session.flush()
    token = generate_jwt(user)

    async def test_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = test_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": f"Bearer {token}"}
            first = await client.post(
                "/api/v1/identity/auth/session/logout", headers=headers
            )
            await db_session.refresh(user)
            second = await client.post(
                "/api/v1/identity/auth/session/logout", headers=headers
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert first.status_code == 200
    assert first.json()["data"]["message"] == "已退出登录"
    assert user.session_version == 1
    assert second.status_code == 401


@pytest.mark.anyio
async def test_password_account_limit_blocks_and_fails_closed(monkeypatch) -> None:
    from app.platform.identity import permission_middleware

    class FakeRedis:
        def __init__(self) -> None:
            self.count = 0
            self.keys: list[str] = []

        async def incr(self, key: str) -> int:
            self.keys.append(key)
            self.count += 1
            return self.count

        async def expire(self, key: str, seconds: int) -> None:
            assert seconds == 900

    fake = FakeRedis()
    monkeypatch.setattr("app.core.redis.redis_client", fake)
    for _ in range(10):
        assert await permission_middleware.check_local_account_rate_limit(" Admin ")
    assert await permission_middleware.check_local_account_rate_limit("admin") is False
    assert all("admin" not in key for key in fake.keys)

    async def unavailable(_: str) -> int:
        raise ConnectionError("redis unavailable")

    fake.incr = unavailable
    assert await permission_middleware.check_local_account_rate_limit("admin") is None


@pytest.mark.anyio
async def test_password_reset_revokes_existing_jwt(db_session: AsyncSession) -> None:
    admin = User(
        name="测试管理员",
        username=f"admin-{uuid4().hex[:12]}",
        role="admin",
        status="active",
        auth_source="local",
        session_version=0,
    )
    target = User(
        name="测试用户",
        username=f"target-{uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
        session_version=0,
    )
    db_session.add_all([admin, target])
    await db_session.flush()
    old_token = generate_jwt(target)

    async def test_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def test_admin() -> User:
        return admin

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = test_admin
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/identity/users/{target.id}/reset-password",
                json={"password": "new-test-password"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    await db_session.refresh(target)
    assert response.status_code == 200
    assert target.session_version == 1
    assert verify_password("new-test-password", target.password_hash)

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {old_token}".encode())],
        }
    )
    assert (
        await get_current_user(request, db_session, get_settings(), auth_token=None)
        is None
    )
