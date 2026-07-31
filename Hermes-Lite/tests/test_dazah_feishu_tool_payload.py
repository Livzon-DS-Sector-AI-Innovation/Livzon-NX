import asyncio
import json

from tools import dazah_platform


def _bind_context() -> object:
    return dazah_platform.dazah_request_context.set(
        {
            "tenant_id": "tenant-test",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "user_name": "测试用户",
            "channel": "feishu",
            "external_binding_id": "00000000-0000-0000-0000-000000000002",
            "trace_id": "00000000-0000-0000-0000-000000000003",
        }
    )


def test_dazah_tool_search_uses_trusted_subject(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [{"operation": "quality.list_deviations"}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            recorded.update(url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setenv("DAZAH_API_BASE_URL", "http://dazah.test/api/v1")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        result = asyncio.run(
            dazah_platform.dazah_tool(
                "search",
                query="偏差",
                module="quality",
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert json.loads(result)["data"][0]["operation"] == "quality.list_deviations"
    assert recorded["url"] == "http://dazah.test/api/v1/agent/tools/search"
    payload = recorded["json"]
    assert payload["subject"]["tenant_id"] == "tenant-test"
    assert payload["subject"]["user_id"].endswith("0001")
    assert "context" not in payload


def test_dazah_tool_execute_does_not_accept_legacy_aliases(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": {"ok": True}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            recorded.update(url=url, json=json)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        asyncio.run(
            dazah_platform.dazah_tool(
                "execute",
                operation="quality.list_deviations",
                params={"page": 1},
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert recorded["url"].endswith("/agent/tools/execute")
    payload = recorded["json"]
    assert payload["operation"] == "quality.list_deviations"
    assert payload["trace_id"].endswith("0003")
    assert "feishu_user_id" not in payload
