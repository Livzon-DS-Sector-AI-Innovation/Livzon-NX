import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.modules.agent import api
from app.modules.agent.schemas import (
    AgentConfirmationResolveRequest,
    AgentToolControlRequest,
    AgentToolEnabledUpdate,
    AgentToolSearchRequest,
)


class Dumpable:
    def __init__(self, **payload) -> None:
        self.payload = payload

    def model_dump(self, **kwargs):
        return self.payload


class FakeDb:
    def __init__(self, user=None) -> None:
        self.user = user
        self.added = []

    async def get(self, model, item_id):
        return self.user

    def add(self, value) -> None:
        self.added.append(value)


class FakeAgentService:
    def __init__(self) -> None:
        self.executed_request = None
        self.cancelled = False
        self.confirmed = False

    async def execute_tool(self, db, *, request):
        self.executed_request = request
        return Dumpable(ok=True, operation=request.operation)

    async def cancel_confirmation(self, db, **kwargs):
        self.cancelled = True
        return SimpleNamespace(id=kwargs["confirmation_id"])

    async def execute_confirmation(self, db, **kwargs):
        self.confirmed = True
        return (
            SimpleNamespace(id=kwargs["confirmation_id"]),
            Dumpable(ok=True, operation="agent.test"),
        )

    def _confirmation_out(self, confirmation):
        return Dumpable(id=str(confirmation.id), status="completed")


class FakeCatalogService:
    def __init__(self) -> None:
        self.enabled = None

    async def list_all(self, db):
        return [Dumpable(operation="agent.test")]

    async def search(self, db, request):
        return [Dumpable(operation="agent.test")]

    async def describe(self, db, **kwargs):
        return Dumpable(operation=kwargs["operation"])

    async def set_enabled(self, db, **kwargs):
        self.enabled = kwargs
        return Dumpable(operation=kwargs["operation"], status="active")


def _subject(user_id: uuid.UUID) -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "user_id": user_id,
        "source": "internal",
    }


def _response_payload(response) -> dict:
    return json.loads(response.body)


@pytest.mark.anyio
async def test_control_plane_tool_routes_delegate_and_enforce_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    admin = SimpleNamespace(
        id=user_id,
        tenant_key="tenant-a",
        role="admin",
    )
    regular = SimpleNamespace(id=uuid.uuid4(), role="user")
    settings = SimpleNamespace(AGENT_TOOL_TOKEN="token")
    db = FakeDb()
    agent_service = FakeAgentService()
    catalog_service = FakeCatalogService()
    monkeypatch.setattr(api, "AgentService", lambda settings: agent_service)
    monkeypatch.setattr(api, "ToolCatalogService", lambda: catalog_service)
    monkeypatch.setattr(api, "require_service_token", lambda *args: None)

    control_response = await api.execute_control_plane_tool(
        AgentToolControlRequest(operation="agent.test", params={"value": 1}),
        db,
        admin,
        settings,
    )
    assert _response_payload(control_response)["data"]["ok"] is True
    assert agent_service.executed_request.subject.user_id == user_id
    assert agent_service.executed_request.execution_context == {
        "source": "admin_control_plane"
    }

    with pytest.raises(HTTPException) as exc:
        await api.list_control_plane_tools(db, regular)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    listed = await api.list_control_plane_tools(db, admin)
    assert _response_payload(listed)["data"] == [{"operation": "agent.test"}]

    searched = await api.search_tools(
        AgentToolSearchRequest.model_validate(
            {"query": "test", "subject": _subject(user_id)}
        ),
        db,
        "Bearer token",
        settings,
    )
    assert _response_payload(searched)["data"] == [{"operation": "agent.test"}]

    described = await api.describe_tool(
        "agent.test",
        user_id,
        db,
        "Bearer token",
        settings,
    )
    assert _response_payload(described)["data"] == {"operation": "agent.test"}

    with pytest.raises(HTTPException) as exc:
        await api.set_tool_enabled(
            "agent.test",
            AgentToolEnabledUpdate(enabled=True),
            db,
            regular,
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    enabled = await api.set_tool_enabled(
        "agent.test",
        AgentToolEnabledUpdate(enabled=True),
        db,
        admin,
    )
    assert _response_payload(enabled)["data"]["status"] == "active"
    assert catalog_service.enabled == {
        "operation": "agent.test",
        "enabled": True,
    }
    assert len(db.added) == 1


@pytest.mark.anyio
async def test_gateway_confirmation_resolution_rejects_untrusted_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    payload = AgentConfirmationResolveRequest.model_validate(
        {"subject": _subject(user_id), "choice": "allow"}
    )
    monkeypatch.setattr(api, "require_service_token", lambda *args: None)

    for user in (
        None,
        SimpleNamespace(is_deleted=True, status="active"),
        SimpleNamespace(is_deleted=False, status="disabled"),
    ):
        with pytest.raises(HTTPException) as exc:
            await api.resolve_confirmation_from_gateway(
                uuid.uuid4(),
                payload,
                FakeDb(user),
                "Bearer token",
                SimpleNamespace(AGENT_TOOL_TOKEN="token"),
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["reject", "allow"])
async def test_gateway_confirmation_resolution_delegates_choice(
    choice: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        is_deleted=False,
        status="active",
    )
    service = FakeAgentService()
    monkeypatch.setattr(api, "require_service_token", lambda *args: None)
    monkeypatch.setattr(api, "AgentService", lambda settings: service)

    response = await api.resolve_confirmation_from_gateway(
        uuid.uuid4(),
        AgentConfirmationResolveRequest.model_validate(
            {"subject": _subject(user_id), "choice": choice}
        ),
        FakeDb(user),
        "Bearer token",
        SimpleNamespace(AGENT_TOOL_TOKEN="token"),
    )

    payload = _response_payload(response)["data"]
    assert payload["confirmation"]["status"] == "completed"
    if choice == "reject":
        assert service.cancelled
        assert "result" not in payload
    else:
        assert service.confirmed
        assert payload["result"]["ok"] is True
