import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/agent/tools/search",
            {
                "query": "time",
                "subject": {
                    "tenant_id": "test",
                    "user_id": str(uuid.uuid4()),
                    "source": "internal",
                },
            },
        ),
        (
            "GET",
            f"/api/v1/agent/tools/agent.get_current_time"
            f"?subject_user_id={uuid.uuid4()}"
            f"&subject_tenant_id=test"
            f"&trace_id={uuid.uuid4()}",
            None,
        ),
        (
            "POST",
            "/api/v1/agent/tools/execute",
            {
                "operation": "agent.get_current_time",
                "subject": {
                    "tenant_id": "test",
                    "user_id": str(uuid.uuid4()),
                    "source": "internal",
                },
            },
        ),
        ("GET", "/api/v1/agent/llm/models", None),
        ("GET", "/api/v1/agent/automations", None),
    ],
)
async def test_agent_http_endpoints_fail_closed_without_credentials(
    client: AsyncClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    response = await client.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/agent/tools/execute/user"),
        ("GET", "/api/v1/agent/tools"),
    ],
)
async def test_removed_tool_endpoints_do_not_exist(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    response = await client.request(method, path)

    assert response.status_code in {404, 405}
