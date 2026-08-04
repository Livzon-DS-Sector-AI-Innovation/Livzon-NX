from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from tools import dazah_platform


def _bind_context() -> object:
    return dazah_platform.dazah_request_context.set(
        {
            "tenant_id": "tenant-contract",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "channel": "internal",
            "trace_id": "00000000-0000-0000-0000-000000000002",
        }
    )


def test_backend_openapi_exposes_progressive_tool_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    paths = document["paths"]
    assert "post" in paths["/api/v1/agent/tools/search"]
    assert "get" in paths["/api/v1/agent/tools/{operation}"]
    assert "post" in paths["/api/v1/agent/tools/execute"]


def test_backend_openapi_exposes_runtime_overview_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))

    operation = document["paths"][
        "/api/v1/agent/control/runtime-overview"
    ]["get"]

    assert operation["operationId"].startswith(
        "get_control_plane_runtime_overview_"
    )
    assert "200" in operation["responses"]
    assert any(
        parameter["name"] == "auth_token" and parameter["in"] == "cookie"
        for parameter in operation["parameters"]
    )


def test_describe_uses_operation_and_trusted_subject(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"data": {"operation": "quality.list_deviations"}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url, params, headers):
            recorded.update(url=url, params=params, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = asyncio.run(
            dazah_platform.dazah_tool(
                "describe",
                operation="quality.list_deviations",
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert json.loads(payload)["data"]["operation"] == "quality.list_deviations"
    assert str(recorded["url"]).endswith(
        "/agent/tools/quality.list_deviations"
    )
    assert recorded["params"] == {
        "subject_user_id": "00000000-0000-0000-0000-000000000001"
    }


def test_timeout_and_unavailable_backend_are_typed_errors(monkeypatch) -> None:
    class FailingAsyncClient:
        failure: type[httpx.HTTPError] = httpx.ReadTimeout

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            request = httpx.Request("POST", url)
            raise self.failure("contract failure", request=request)

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FailingAsyncClient)
    token = _bind_context()
    try:
        for failure in (httpx.ReadTimeout, httpx.ConnectError):
            FailingAsyncClient.failure = failure
            result = asyncio.run(
                dazah_platform.dazah_tool("search", query="偏差")
            )
            assert json.loads(result)["error"] == failure.__name__
    finally:
        dazah_platform.dazah_request_context.reset(token)


def test_tool_schema_has_only_progressive_actions() -> None:
    action = dazah_platform.DAZAH_TOOL_SCHEMA["parameters"]["properties"]["action"]
    assert action["enum"] == ["search", "describe", "execute"]
    assert dazah_platform.DAZAH_TOOL_SCHEMA["parameters"]["required"] == ["action"]
