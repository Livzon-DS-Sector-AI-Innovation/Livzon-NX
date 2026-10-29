"""A service token alone must never authorize a caller-selected user."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.schemas import AgentToolExecuteResponse, AgentTrustedSubject
from app.platform.identity.agent_delegation import (
    issue_agent_delegation,
    require_agent_delegation,
)
from app.platform.identity.models import User


async def test_execute_rejects_service_token_without_user_delegation(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(
        api, "AgentService", lambda _: SimpleNamespace(execute_tool=execute)
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        AGENT_TOOL_TOKEN="synthetic-service", SECRET_KEY="x" * 40
    )
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(get=AsyncMock())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/tools/execute",
            headers={"Authorization": "Bearer synthetic-service"},
            json={
                "operation": "agent.get_current_time",
                "subject": {
                    "user_id": str(uuid4()),
                    "tenant_id": "default",
                    "source": "web",
                },
            },
        )
    assert response.status_code == 401
    execute.assert_not_awaited()


def _identity():
    return User(
        id=uuid4(),
        name="audit",
        tenant_key="factory",
        status="active",
        is_deleted=False,
        session_version=7,
    )


@pytest.mark.parametrize(
    "alteration", ["user", "tenant", "source", "signature", "none"]
)
async def test_signed_identity_cannot_be_substituted(alteration):
    user = _identity()
    settings = SimpleNamespace(SECRET_KEY="x" * 40)
    token = issue_agent_delegation(settings, user, source="web")
    user_id, tenant, source = user.id, "factory", "web"
    if alteration == "user":
        user_id = uuid4()
    if alteration == "tenant":
        tenant = "another-factory"
    if alteration == "source":
        source = "automation"
    if alteration == "signature":
        token = token[:-8] + "tampered"
    if alteration == "none":
        token = None
    db = SimpleNamespace(get=AsyncMock(return_value=user))
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await require_agent_delegation(
            db, settings, token, user_id=user_id, tenant_id=tenant, source=source
        )
    assert error.value.status_code == 401
    db.get.assert_not_awaited()


@pytest.mark.parametrize("revocation", ["logout", "disabled", "deleted"])
async def test_delegation_rechecks_current_user_state(revocation):
    user = _identity()
    settings = SimpleNamespace(SECRET_KEY="x" * 40)
    token = issue_agent_delegation(settings, user, source="web")
    if revocation == "logout":
        user.session_version += 1
    if revocation == "disabled":
        user.status = "disabled"
    if revocation == "deleted":
        user.is_deleted = True
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await require_agent_delegation(
            SimpleNamespace(get=AsyncMock(return_value=user)),
            settings,
            token,
            user_id=user.id,
            tenant_id="factory",
            source="web",
        )
    assert error.value.status_code == 403


async def test_valid_delegation_reaches_executor_without_logging_credential(
    monkeypatch,
):
    user = _identity()
    settings = SimpleNamespace(
        SECRET_KEY="x" * 40, AGENT_TOOL_TOKEN="synthetic-service"
    )
    token = issue_agent_delegation(settings, user, source="web")
    execute = AsyncMock(
        return_value=AgentToolExecuteResponse(
            ok=True, operation="agent.get_current_time"
        )
    )
    monkeypatch.setattr(
        api, "AgentService", lambda _: SimpleNamespace(execute_tool=execute)
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(
        get=AsyncMock(return_value=user)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/tools/execute",
            headers={
                "Authorization": "Bearer synthetic-service",
                "X-Dazah-Delegation": token,
            },
            json={
                "operation": "agent.get_current_time",
                "subject": {
                    "user_id": str(user.id),
                    "tenant_id": "factory",
                    "source": "web",
                },
            },
        )
    assert response.status_code == 200
    execute.assert_awaited_once()
    assert token not in response.text
    subject = AgentTrustedSubject(
        user_id=user.id, tenant_id="factory", source="web", delegation_token=token
    )
    assert "delegation_token" not in subject.model_dump()
    assert token not in repr(subject)


@pytest.mark.parametrize("operation", ["search", "describe", "confirmation"])
async def test_other_service_identity_routes_also_require_delegation(operation):
    user_id = str(uuid4())
    subject = {"user_id": user_id, "tenant_id": "factory", "source": "feishu"}
    db = SimpleNamespace(get=AsyncMock())
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        SECRET_KEY="x" * 40, AGENT_TOOL_TOKEN="synthetic-service"
    )
    headers = {"Authorization": "Bearer synthetic-service"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if operation == "describe":
            response = await client.get(
                "/agent/tools/agent.get_current_time",
                headers=headers,
                params={
                    "subject_user_id": user_id,
                    "subject_tenant_id": "factory",
                    "trace_id": str(uuid4()),
                },
            )
        else:
            path = (
                "/agent/tools/search"
                if operation == "search"
                else f"/agent/confirmations/{uuid4()}/resolve"
            )
            response = await client.post(
                path,
                headers=headers,
                json={
                    "subject": subject,
                    **(
                        {"query": "test"}
                        if operation == "search"
                        else {"choice": "allow"}
                    ),
                },
            )
    assert response.status_code == 401
    db.get.assert_not_awaited()
