from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.modules.agent import api, service
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.page_context import resolve_page_context
from app.modules.agent.schemas import AgentPageContext
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGE_DEFINITIONS


@pytest.mark.asyncio
async def test_page_hints_are_resolved_from_live_grants_not_client_authority(
    monkeypatch,
):
    page = next(p for p in PAGE_DEFINITIONS if p.module_code == "production")
    grants = AsyncMock(
        return_value=[SimpleNamespace(page_key=page.page_key, permissions=["query"])]
    )
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    hint = {
        "route_path": page.route_path,
        "page_key": "spoof",
        "user_id": "spoof",
        "filters": {"status": "open", "token": "private", "keyword": "x" * 201},
    }
    result = await resolve_page_context(object(), user=object(), hint=hint)
    assert result.page_key == page.page_key and result.page_name == page.page_name
    assert result.filters == {"status": "open"}
    grants.return_value = []
    assert await resolve_page_context(object(), user=object(), hint=hint) is None
    grants.side_effect = HTTPException(403, "scope unavailable")
    with pytest.raises(HTTPException):
        await resolve_page_context(object(), user=object(), hint=hint)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hint",
    [
        None,
        "text",
        {},
        {"route_path": "https://untrusted/page"},
        {"route_path": "/settings"},
        {"route_path": "/x" * 301},
    ],
)
async def test_unknown_or_management_routes_do_not_become_business_context(
    monkeypatch, hint
):
    grants = AsyncMock()
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    assert await resolve_page_context(object(), user=object(), hint=hint) is None
    grants.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_hermes_request_forwards_page_hints_separately_from_trusted_subject(
    monkeypatch,
    stream,
):
    captured = []
    ensure_agent_tools_registered()

    def handler(request):
        import json

        captured.append(json.loads(request.content))
        if stream:
            body = captured[-1]
            event = {
                "protocol_version": "2.0",
                "event_id": str(uuid4()),
                "trace_id": body["trace_id"],
                "run_id": body["run_id"],
                "sequence": 1,
                "occurred_at": "2026-10-10T00:00:00Z",
                "type": "finished",
                "data": {"message": "ready"},
            }
            return httpx.Response(
                200,
                text="event: finished\ndata: " + json.dumps(event) + "\n\n",
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(200, json={"message": "ready"})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = Settings(
        _env_file=None, HERMES_AGENT_V2_URL="http://hermes/v2/agent/runs"
    )
    user = SimpleNamespace(id=uuid4(), tenant_key="tenant", name="User")
    page = next(p for p in PAGE_DEFINITIONS if p.module_code == "production")
    context = AgentPageContext(
        page_key=page.page_key,
        page_name=page.page_name,
        module_code=page.module_code,
        route_path=page.route_path,
    )
    agent = service.AgentService(settings)
    kwargs = dict(
        session_id=uuid4(),
        user=user,
        message="分析当前页面",
        context={"page_context": context.model_dump()},
        history=[],
    )
    if stream:
        events = [event async for event in agent._call_hermes_stream(**kwargs)]
        assert events[-1].type == "finished"
    else:
        await agent._call_hermes(**kwargs)
    assert captured[0]["page_context"]["page_key"] == page.page_key
    assert captured[0]["subject"]["user_id"] == str(user.id)
    assert "page_context" not in captured[0]["subject"]


@pytest.mark.asyncio
async def test_live_tool_descriptor_http_exposes_source_semantics_and_denies_revocation(
    monkeypatch,
):
    ensure_agent_tools_registered()
    spec = tool_registry.require("registration.read_knowledge_article")
    row = SimpleNamespace(
        operation=spec.name,
        module=spec.module,
        capability_version="1.0",
        summary=spec.summary,
        status="active",
        admin_enabled=True,
        risk_level=spec.risk_level,
        write=False,
        confirmation_required=False,
        permission_key=spec.permission_key,
        input_schema=spec.input_model.model_json_schema(),
        output_schema=spec.output_schema,
        timeout_seconds=30,
        idempotent=False,
    )
    user = SimpleNamespace(
        id=uuid4(), status="active", is_deleted=False, tenant_key="tenant"
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=row),
        get=AsyncMock(return_value=user),
        add=lambda _: None,
    )
    monkeypatch.setattr(ToolCatalogService, "synchronize", AsyncMock())
    from app.modules.agent.access_scope import AgentAccessScopeService

    access = AsyncMock()
    monkeypatch.setattr(AgentAccessScopeService, "require_tool_access", access)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/agent")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, AGENT_TOOL_TOKEN="test-only"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        params = {
            "subject_user_id": str(user.id),
            "subject_tenant_id": "tenant",
            "trace_id": str(uuid4()),
        }
        response = await client.get(
            f"/api/v1/agent/tools/{spec.name}",
            params=params,
            headers={"Authorization": "Bearer test-only"},
        )
        assert response.status_code == 200
        descriptor = response.json()["data"]
        assert descriptor["result_kind"] == "knowledge"
        assert "正文" in descriptor["output_hint"]
        assert descriptor["input_schema"]["required"] == ["article_id"]
        access.side_effect = HTTPException(403, "revoked")
        denied = await client.get(
            f"/api/v1/agent/tools/{spec.name}",
            params=params,
            headers={"Authorization": "Bearer test-only"},
        )
        assert denied.status_code == 403


def test_analytics_descriptor_contains_executable_json_schema():
    ensure_agent_tools_registered()
    spec = tool_registry.require("analytics.aggregate")
    assert spec.result_kind == "statistics"
    assert spec.input_schema["type"] == "object"
    assert "metrics" in spec.input_schema["properties"]
    assert spec.input_schema["examples"]
