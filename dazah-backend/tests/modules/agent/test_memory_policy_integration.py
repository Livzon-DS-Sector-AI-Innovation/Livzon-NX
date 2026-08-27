import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.main import app
from app.modules.agent.memory_policy import AgentMemoryPolicyService
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User


def _user(*, role: str = "user", tenant_key: str | None = None) -> User:
    suffix = uuid.uuid4().hex[:12]
    return User(
        id=uuid.uuid4(),
        name="记忆治理测试用户",
        username=f"memory-{suffix}",
        role=role,
        status="active",
        auth_source="local",
        tenant_key=tenant_key or f"memory-tenant-{suffix}",
    )


@pytest.mark.anyio
async def test_user_mode_pause_resume_and_restriction_source_persist(
    db_session: Any,
) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    service = AgentMemoryPolicyService(Settings())

    assert "已暂停" in await service.handle_command(  # type: ignore[operator]
        db_session, user=user, message="/memory pause", private_channel=True
    )
    status = await service.handle_command(
        db_session, user=user, message="/memory status", private_channel=True
    )
    assert status is not None
    assert "全局上限" in status
    assert "生效来源：个人选择" in status

    resumed = await service.handle_command(
        db_session, user=user, message="/memory resume", private_channel=True
    )
    assert resumed is not None and "自动记忆" in resumed


@pytest.mark.anyio
async def test_clear_confirmation_is_one_time_and_hermes_receives_marker(
    db_session: Any, monkeypatch: Any
) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    service = AgentMemoryPolicyService(Settings())
    control: Any = AsyncMock(return_value={"cleared": True})
    monkeypatch.setattr(service, "_hermes_control", control)

    prompt = await service.handle_command(
        db_session, user=user, message="/memory clear", private_channel=True
    )
    confirmed = await service.handle_command(
        db_session,
        user=user,
        message="/memory clear confirm",
        private_channel=True,
    )
    repeated = await service.handle_command(
        db_session,
        user=user,
        message="/memory clear confirm",
        private_channel=True,
    )

    assert prompt is not None and "5分钟" in prompt
    assert confirmed is not None and "在线长期记忆已清空" in confirmed
    assert repeated is not None and "不存在或已过期" in repeated
    control.assert_awaited_once()
    assert control.await_args.kwargs["cleared_at"] is not None


@pytest.mark.anyio
async def test_tenant_policy_api_requires_admin_validates_and_only_tightens(
    client: Any, db_session: Any
) -> None:
    assert (await client.get("/api/v1/agent/memory/tenant-policy")).status_code == 401

    regular = _user(role="user")

    async def regular_user() -> User:
        return regular

    app.dependency_overrides[get_current_user] = regular_user
    try:
        assert (
            await client.get("/api/v1/agent/memory/tenant-policy")
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    admin = _user(role="admin")
    db_session.add(admin)
    await db_session.commit()

    async def admin_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = admin_user
    try:
        invalid = await client.put(
            "/api/v1/agent/memory/tenant-policy", json={"mode": "invalid"}
        )
        tightened = await client.put(
            "/api/v1/agent/memory/tenant-policy",
            json={"mode": "explicit_only"},
        )
        relaxed = await client.put(
            "/api/v1/agent/memory/tenant-policy", json={"mode": "auto"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert invalid.status_code == 422
    assert tightened.status_code == 200
    assert tightened.json()["tenant_mode"] == "explicit_only"
    assert relaxed.status_code == 409
