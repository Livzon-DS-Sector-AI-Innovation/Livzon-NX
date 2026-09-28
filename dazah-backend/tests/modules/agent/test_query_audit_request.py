"""Query audit snapshots through HTTP, using in-memory dependencies only."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.schemas import (
    AgentAutomationOut,
    AgentAutomationPage,
    AgentToolCatalogEntry,
)
from app.platform.audit import middleware
from app.platform.audit.middleware import AuditMiddleware
from app.platform.audit.models import AuditLog
from app.platform.identity.deps import require_current_user
from app.platform.identity.models import User


class AuditSession:
    def __init__(self) -> None:
        self.records: list[AuditLog] = []

    async def __aenter__(self) -> "AuditSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def add(self, record: AuditLog) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        pass


def query_app(
    monkeypatch: pytest.MonkeyPatch, session: AuditSession, actor: User
) -> FastAPI:
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/agent")
    app.add_middleware(AuditMiddleware)
    monkeypatch.setattr(middleware, "async_session_factory", lambda: session)

    async def database() -> Any:
        return session

    async def current_user(request: Request) -> User:
        request.state.audit_user_id = actor.id
        return actor

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_current_user] = current_user
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["populated", "empty", "forbidden"])
async def test_automation_query_saves_bounded_result_and_request_link(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    actor = User(id=uuid4(), role="admin")
    session = AuditSession()
    app = query_app(monkeypatch, session, actor)
    item = AgentAutomationOut(
        id=uuid4(),
        owner_user_id=actor.id,
        name="偏差日报",
        description="private-description",
        scope_type="platform",
        status="enabled",
        scope_ref={"api_key": "private-key"},
    )
    result = AgentAutomationPage(
        items=[item] if outcome == "populated" else [],
        page=2,
        page_size=20,
        total=21 if outcome == "populated" else 0,
    )
    query = AsyncMock(
        return_value=result,
        side_effect=HTTPException(403, "无平台查询权限")
        if outcome == "forbidden"
        else None,
    )
    monkeypatch.setattr(api.AgentAutomationService, "list_automations", query)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/agent/automations?scope=platform&page=2&page_size=20"
        )
    assert response.status_code == (403 if outcome == "forbidden" else 200)
    if outcome == "forbidden":
        assert response.json()["detail"] == "无平台查询权限"
        assert [record.action for record in session.records] == ["platform_api_request"]
        return
    assert response.json()["data"] == result.model_dump(mode="json")
    event, operation = session.records
    assert event.request_id == operation.request_id == response.headers["X-Request-ID"]
    assert event.action == "list_agent_automations"
    assert event.old_value is None
    assert event.new_value["total"] == result.total
    assert event.new_value["page"] == 2
    assert event.new_value["page_size"] == 20
    assert len(event.new_value["items"]) == len(result.items)
    assert event.extra["returned"] == len(result.items)
    assert event.extra["request"] == {
        "scope": "platform",
        "status": None,
        "page": 2,
        "page_size": 20,
    }
    if result.items:
        assert event.new_value["items"][0]["id"] == str(item.id)
        assert event.new_value["items"][0]["name"] == "偏差日报"
    assert "private" not in str(event.new_value)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["populated", "empty", "forbidden"])
async def test_tool_search_records_result_and_http_metadata_without_query_text(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    actor = User(id=uuid4(), role="admin")
    session = AuditSession()
    app = query_app(monkeypatch, session, actor)

    # Replace authentication with a deterministic fake; never load a real service token.
    def authenticate(_expected: str, authorization: str | None) -> None:
        if outcome == "forbidden":
            raise HTTPException(401, "Service authorization required")
        assert authorization == "Bearer audit-test"

    monkeypatch.setattr(api, "require_service_token", authenticate)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        AGENT_TOOL_TOKEN=""
    )
    result = (
        [
            AgentToolCatalogEntry(
                operation="quality.list_deviations",
                module="quality",
                summary="查询偏差记录",
                version="1",
                status="active",
                risk_level="low",
                write=False,
                confirmation_required=False,
                timeout_seconds=30,
                idempotent=True,
                input_schema={"private": "omitted"},
                output_schema={"private": "omitted"},
            )
        ]
        if outcome == "populated"
        else []
    )
    query = AsyncMock(return_value=result)
    monkeypatch.setattr(api.ToolCatalogService, "search", query)
    trace_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/agent/tools/search",
            headers={
                "Authorization": "Bearer audit-test",
                "User-Agent": "audit-client",
            },
            json={
                "query": "private business query",
                "module": "quality",
                "limit": 12,
                "trace_id": str(trace_id),
                "subject": {
                    "user_id": str(actor.id),
                    "tenant_id": "test",
                    "source": "internal",
                },
            },
        )
    assert response.status_code == (401 if outcome == "forbidden" else 200)
    if outcome == "forbidden":
        query.assert_not_awaited()
        assert session.records == []
        return
    assert response.json()["data"] == [item.model_dump(mode="json") for item in result]
    (event,) = session.records
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.extra["trace_id"] == str(trace_id)
    assert event.duration_ms is not None and event.duration_ms >= 0
    assert event.ip_address == "127.0.0.1"
    assert event.user_agent == "audit-client"
    assert event.new_value["result_count"] == len(result)
    assert len(event.new_value["items"]) == len(result)
    assert event.extra["request"]["limit"] == 12
    assert event.extra["request"]["query_length"] == len("private business query")
    if result:
        assert event.new_value["items"][0]["operation"] == "quality.list_deviations"
    assert "private" not in str(event.new_value) + str(event.extra)
