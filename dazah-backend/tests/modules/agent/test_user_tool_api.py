import json
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.modules.agent.api import execute_tool_as_current_user
from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.service import AgentService


@pytest.mark.anyio
async def test_user_tool_endpoint_uses_authenticated_user_identity(monkeypatch) -> None:
    authenticated_user_id = uuid.uuid4()
    supplied_user_id = uuid.uuid4()
    captured_request = None

    async def fake_execute_tool(self, db, *, request):
        nonlocal captured_request
        captured_request = request
        return SimpleNamespace(
            model_dump=lambda **_: {
                "ok": True,
                "operation": request.operation,
                "requires_confirmation": True,
            }
        )

    monkeypatch.setattr(AgentService, "execute_tool", fake_execute_tool)

    response = await execute_tool_as_current_user(
        payload=AgentToolExecuteRequest(
            operation="agent.set_automation_enabled",
            body={"automation_id": str(uuid.uuid4()), "enabled": True},
            context={
                "source": "settings_livzon_task",
                "user_id": str(supplied_user_id),
            },
        ),
        db=object(),
        current_user=SimpleNamespace(id=authenticated_user_id),
        settings=SimpleNamespace(),
    )

    assert captured_request is not None
    assert captured_request.context == {
        "source": "settings_livzon_task",
        "user_id": str(authenticated_user_id),
    }
    assert json.loads(response.body)["data"]["requires_confirmation"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/agent/tools/execute/user",
            {"operation": "agent.get_current_time"},
        ),
        (
            "POST",
            "/api/v1/agent/tools/execute",
            {"operation": "agent.get_current_time"},
        ),
        ("GET", "/api/v1/agent/tools", None),
        ("GET", "/api/v1/agent/llm/models", None),
        ("GET", "/api/v1/agent/automations", None),
        (
            "POST",
            f"/api/v1/agent/confirmations/{uuid.uuid4()}/execute",
            None,
        ),
    ],
)
async def test_agent_http_endpoints_fail_closed_without_credentials(
    client: AsyncClient,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    response = await client.request(method, path, json=payload)

    assert response.status_code == 401
