from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "services" / "dazah_agent_service.py"
PLATFORM_TOOL_SOURCE = Path(__file__).resolve().parents[1] / "tools" / "dazah_platform.py"


def test_dazah_prompt_discovers_business_tools_from_live_directory() -> None:
    from services.dazah_agent_service import _system_prompt

    prompt = _system_prompt()
    assert "以当前主体的实时工具目录为准" in prompt
    assert "describe" in prompt and "execute" in prompt
    assert "quality.list_deviation_report_records" not in prompt


def test_skill_resolver_default_scope_includes_quality() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert 'default_scope = ["identity", "energy", "warehouse", "procurement", "quality"]' in source
    assert '"business_scope": _business_scope(payload.context)' in source


def test_quality_requests_do_not_bypass_agent_orchestration() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    platform_source = PLATFORM_TOOL_SOURCE.read_text(encoding="utf-8")

    assert 'enum": ["search", "describe", "execute"]' in platform_source
    assert "ALLOWED_OPERATIONS" not in platform_source
    assert "def _try_direct_quality_response" not in source
    assert "_try_direct_quality_response(payload)" not in source


def test_energy_feishu_config_writes_route_through_confirmed_tools(monkeypatch) -> None:
    import asyncio
    import json

    import httpx

    from tools import dazah_platform as platform

    operation = "energy.create_feishu_source_root"
    real_client = httpx.AsyncClient

    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"operation": operation, "write": True, "confirmation_required": True}})
        return httpx.Response(200, json={"data": {
            "ok": True, "requires_confirmation": True,
            "confirmation": {"id": "pending-test", "status": "pending", "operation": operation},
        }})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    platform.register_dazah_task_context("energy-write", {"user_id": "u", "tenant_id": "t"})
    try:
        asyncio.run(platform.dazah_tool("describe", operation=operation, task_id="energy-write"))
        response = json.loads(asyncio.run(platform.dazah_tool("execute", operation=operation, task_id="energy-write")))
        assert response["data"]["requires_confirmation"] is True
        assert platform.current_dazah_task_confirmations("energy-write")[0]["id"] == "pending-test"
        fact = platform.current_dazah_task_evidence("energy-write")[-1]
        assert fact.write is True and fact.confirmation_id == "pending-test" and fact.data is None
    finally:
        platform.unregister_dazah_task_context("energy-write")
