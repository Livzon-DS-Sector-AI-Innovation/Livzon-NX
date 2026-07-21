import uuid

import pytest

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User


def _user(*, role: str) -> User:
    return User(
        id=uuid.uuid4(),
        name="审计接口测试用户",
        username=f"audit-api-{uuid.uuid4().hex[:12]}",
        role=role,
        status="active",
        auth_source="local",
    )


@pytest.mark.asyncio
async def test_general_audit_logs_require_admin_and_exclude_conversations(
    client,
) -> None:
    unauthenticated = await client.get(
        "/api/v1/audit/logs",
        params={"category": "business"},
    )
    assert unauthenticated.status_code == 401

    regular_user = _user(role="user")

    async def override_regular_user() -> User:
        return regular_user

    app.dependency_overrides[get_current_user] = override_regular_user
    try:
        forbidden = await client.get(
            "/api/v1/audit/logs",
            params={"category": "business"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert forbidden.status_code == 403

    admin = _user(role="admin")

    async def override_admin() -> User:
        return admin

    app.dependency_overrides[get_current_user] = override_admin
    try:
        response = await client.get(
            "/api/v1/audit/logs",
            params={"category": "business", "page": 1, "page_size": 20},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert all(item["category"] == "business" for item in data["items"])
    assert all(
        item["action"]
        not in {"list_agent_conversation_audit", "view_agent_conversation_audit"}
        for item in data["items"]
    )
