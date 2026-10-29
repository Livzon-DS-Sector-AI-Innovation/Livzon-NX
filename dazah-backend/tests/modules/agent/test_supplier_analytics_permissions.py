from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity.agent_delegation import issue_agent_delegation
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("permissions", "scope_type", "stale", "expected"),
    [
        (["access", "query"], "all", False, 200),
        (["access"], "all", False, 403),
        ([], "all", False, 403),
        (["access", "query"], "department_tree", False, 403),
        (["access", "query"], "all", True, 403),
    ],
)
async def test_analytics_http_enforces_page_scope_and_revocation(
    monkeypatch, permissions, scope_type, stale, expected
):
    ensure_agent_tools_registered()
    original = tool_registry.require("analytics.aggregate")
    monkeypatch.setitem(
        tool_registry._tools,
        original.name,
        replace(original, required_roles=("admin",)),
    )
    user = SimpleNamespace(
        id=uuid4(), role="user", status="active", is_deleted=False, grant_version=2,
        tenant_key="local", session_version=0,
    )
    snapshot = SimpleNamespace(
        source_grant_version=1 if stale else 2,
        sync_status="synced",
        registry_version="current",
        tool_names=["analytics.aggregate"],
        workflow_tool_names=["analytics.aggregate"],
    )
    scope_service = AgentAccessScopeService()
    monkeypatch.setattr(scope_service, "get_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(scope_service, "current_registry_version", lambda: "current")
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[
                EffectivePageGrantOut(
                    page_key="purchasing:supplier",
                    module_code="procurement",
                    permissions=permissions,
                    data_scope=PageDataScopeInput(scope_type=scope_type),
                    source="role",
                )
            ]
        ),
    )
    execute_query = AsyncMock(
        return_value=SimpleNamespace(
            all=lambda: [SimpleNamespace(_mapping={"count": 3})]
        )
    )
    db = SimpleNamespace(get=AsyncMock(return_value=user), execute=execute_query)
    repo = SimpleNamespace(
        create_tool_call=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        finish_tool_call=AsyncMock(),
    )
    executor = ToolExecutor(repo=repo, access_scope_service=scope_service)
    monkeypatch.setattr(executor, "_write_audit", AsyncMock())
    monkeypatch.setattr(
        api,
        "AgentService",
        lambda settings: SimpleNamespace(execute_tool=executor.execute),
    )
    settings = SimpleNamespace(
        AGENT_TOOL_TOKEN="unit-service-token", SECRET_KEY="a" * 40
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/agent")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/agent/tools/execute",
            headers={
                "Authorization": "Bearer unit-service-token",
                "X-Dazah-Delegation": issue_agent_delegation(
                    settings, user, source="internal"
                ),
            },
            json={
                "operation": "analytics.aggregate",
                "params": {"dataset": "procurement.suppliers"},
                "subject": {
                    "user_id": str(user.id),
                    "tenant_id": "local",
                    "source": "internal",
                },
            },
        )
    assert response.status_code == expected
    if expected == 200:
        result = response.json()["data"]
        assert result["ok"] is True
        assert result["operation"] == "analytics.aggregate"
        assert result["data"]["rows"] == [{"count": 3}]
        assert result["data"]["dataset"]["name"] == "procurement.suppliers"
        execute_query.assert_awaited_once()
    else:
        assert response.json()["detail"]
        execute_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_analytics_scope_is_removed_without_supplier_query_grant(monkeypatch):
    ensure_agent_tools_registered()
    service = AgentAccessScopeService()
    user = SimpleNamespace(id=uuid4(), role="user", is_deleted=False, grant_version=1)
    grants = []
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(side_effect=lambda *args, **kwargs: grants),
    )
    monkeypatch.setattr(service, "get_snapshot", AsyncMock(return_value=None))
    db = SimpleNamespace(
        get=AsyncMock(return_value=user), add=lambda value: None, flush=AsyncMock()
    )
    snapshot = await service.synchronize(db, user_id=user.id)
    assert "analytics.aggregate" not in snapshot.tool_names
    grants.append(
        EffectivePageGrantOut(
            page_key="purchasing:supplier",
            module_code="procurement",
            permissions=["access", "query"],
            data_scope=PageDataScopeInput(scope_type="all"),
            source="role",
        )
    )
    granted = await service.synchronize(db, user_id=user.id)
    assert "analytics.aggregate" in granted.tool_names
    assert "analytics.aggregate" in granted.workflow_tool_names
    grants.clear()
    user.grant_version += 1
    revoked = await service.synchronize(db, user_id=user.id)
    assert "analytics.aggregate" not in revoked.tool_names
    assert "analytics.aggregate" not in revoked.workflow_tool_names
