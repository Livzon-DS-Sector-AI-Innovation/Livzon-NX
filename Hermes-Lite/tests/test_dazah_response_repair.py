import asyncio
import json
import threading
import uuid

import httpx
import pytest

from services import dazah_agent_service as service
from tools import dazah_platform as platform
from tools import lark_cli as lark


def payload():
    return service.AgentBackendV2Request(
        protocol_version="2.0", run_id=uuid.uuid4(), trace_id=uuid.uuid4(),
        session_id="repair-test", message="帮我看看仓储最近的记录",
        subject={"tenant_id": "tenant-test", "user_id": "user-test", "source": "web"},
        source={"platform": "web"},
    )


def test_unverified_answer_is_repaired_with_current_run_evidence(monkeypatch):
    calls = []
    deltas = []

    async def catalog(**kwargs):
        platform.record_dazah_task_tool_trace(kwargs["task_id"], {
            "action": "search", "ok": True, "capabilities": [{
                "operation": "warehouse.list_page_records", "summary": "查询仓储记录", "write": False,
            }],
        })
        return json.dumps({"data": []})

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **kwargs):
            pass

        def run_conversation(self, message, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                if kwargs["stream_callback"]:
                    kwargs["stream_callback"]("FAKE-001")
                return {"final_response": "Dazah 平台查询结果 warehouse.list_page_records：FAKE-001"}
            assert platform.current_dazah_request_context(kwargs["task_id"])["_read_only_repair"] is True
            assert self.max_iterations <= 4
            platform.record_dazah_task_tool_trace(kwargs["task_id"], {
                "action": "execute", "operation": "warehouse.list_page_records", "ok": True,
            })
            return {"final_response": "查询结果：warehouse.list_page_records，本轮为空。"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    monkeypatch.setattr(service, "dazah_tool", catalog)
    _, result = service._run_agent_conversation(payload(), stream_callback=deltas.append)
    assert len(calls) == 2
    assert calls[1]["persist_user_message"] is None
    assert "本轮为空" in result["final_response"]
    assert "FAKE-001" not in "".join(deltas)
    assert any(item.get("action") == "repair" for item in result["tool_trace"])


@pytest.mark.parametrize("write", [True, None])
def test_repair_gateway_blocks_writes_and_unknown_operations(monkeypatch, write):
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    platform.register_dazah_task_context("repair-guard", {"user_id": "u", "tenant_id": "t"})
    platform.record_dazah_task_tool_trace("repair-guard", {
        "action": "describe", "ok": True, "capabilities": [{"operation": "custom.change", "write": write}],
    })
    platform.enable_dazah_task_read_only_repair("repair-guard")
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.change", task_id="repair-guard")))
        assert result["ok"] is False
        assert result["error"] == "repair_read_only"
    finally:
        platform.unregister_dazah_task_context("repair-guard")


def test_repair_read_requires_successful_describe_and_has_call_budget(monkeypatch):
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json={"ok": True, "data": {"items": []}}))
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    platform.register_dazah_task_context("repair-guard", {"user_id": "u", "tenant_id": "t"})
    platform.record_dazah_task_tool_trace("repair-guard", {
        "action": "describe", "ok": True, "capabilities": [{"operation": "custom.read", "write": False}],
    })
    platform.enable_dazah_task_read_only_repair("repair-guard", max_calls=1)
    try:
        first = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.read", task_id="repair-guard")))
        second = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.read", task_id="repair-guard")))
        assert first["ok"] is True
        assert second["error"] == "repair_budget_exhausted"
    finally:
        platform.unregister_dazah_task_context("repair-guard")


def test_repair_cannot_use_feishu_side_channel():
    platform.register_dazah_task_context("repair-guard", {"user_id": "u", "tenant_id": "t"})
    platform.enable_dazah_task_read_only_repair("repair-guard")
    try:
        result = json.loads(asyncio.run(lark.lark_cli(["docs", "+update"], task_id="repair-guard")))
        assert result["error"] == "repair_read_only"
    finally:
        platform.unregister_dazah_task_context("repair-guard")


def test_cancelled_run_cannot_start_tool_repair(monkeypatch):
    cancellation = threading.Event()
    cancellation.set()
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    platform.register_dazah_task_context("repair-guard", {
        "user_id": "u", "tenant_id": "t", "_cancellation_event": cancellation,
    })
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("search", task_id="repair-guard")))
        assert result["error"] == "run_cancelled"
    finally:
        platform.unregister_dazah_task_context("repair-guard")


@pytest.mark.parametrize("cause", ["denied", "write", "pending"])
def test_authorization_and_write_evidence_prevent_automatic_replay(monkeypatch, cause):
    calls = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            calls.append(kwargs)
            task_id = kwargs["task_id"]
            if cause == "pending":
                platform.record_dazah_task_confirmation(task_id, {"id": "confirmation-test", "status": "pending"})
            else:
                platform.record_dazah_task_tool_trace(task_id, {
                    "action": "execute" if cause == "write" else "search",
                    "operation": "custom.change" if cause == "write" else None,
                    "ok": cause == "write", "status_code": 403 if cause == "denied" else 200,
                })
            return {"final_response": "查询结果：warehouse.list_page_records，FAKE-001"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    _, result = service._run_agent_conversation(payload())
    assert len(calls) == 1
    assert not any(item.get("action") == "repair" for item in result["tool_trace"])
    if cause != "pending":
        assert "FAKE-001" not in result["final_response"]
        assert "Trace ID" in result["final_response"]
    else:
        checked = service._verified_agent_message(
            result["final_response"], result["current_pending_confirmations"], result["tool_trace"],
        )
        assert "FAKE-001" not in checked
        assert "真实待确认项" in checked


def test_repair_exhaustion_reports_verified_progress_and_next_step(monkeypatch):
    calls = []

    async def catalog(**kwargs):
        platform.record_dazah_task_tool_trace(kwargs["task_id"], {
            "action": "search", "ok": True,
            "capabilities": [{"operation": "custom.read_records", "summary": "自定义记录查询", "write": False}],
        })
        return "{}"

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            calls.append(kwargs)
            return {"final_response": "查询结果：custom.read_records，FAKE-001"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    monkeypatch.setattr(service, "dazah_tool", catalog)
    agent, result = service._run_agent_conversation(payload())
    assert len(calls) == 2
    assert agent.max_iterations == 30
    assert "FAKE-001" not in result["final_response"]
    assert "自定义记录查询" in result["final_response"]
    assert "下一步" in result["final_response"] or "请明确" in result["final_response"]
    assert "已尝试一次只读修复" in result["final_response"]
    assert any(item.get("status") == "exhausted" for item in result["tool_trace"])


def test_repair_gateway_never_repeats_completed_read(monkeypatch):
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    platform.register_dazah_task_context("repair-guard", {"user_id": "u", "tenant_id": "t"})
    platform.record_dazah_task_tool_trace("repair-guard", {
        "action": "describe", "ok": True, "capabilities": [{"operation": "custom.read", "write": False}],
    })
    platform.record_dazah_task_tool_trace("repair-guard", {"action": "execute", "operation": "custom.read", "ok": True})
    platform.enable_dazah_task_read_only_repair("repair-guard")
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.read", task_id="repair-guard")))
        assert result["error"] == "repair_already_completed"
    finally:
        platform.unregister_dazah_task_context("repair-guard")


def test_capability_question_enters_agent_instead_of_basic_command_shortcut(monkeypatch):
    request = payload()
    request.message = "你可以做些什么"
    queries = []

    async def catalog(**kwargs):
        queries.append(kwargs["query"])
        entries = [] if kwargs["query"] else [{"operation": "custom.read", "summary": "读取授权页面"}]
        platform.record_dazah_task_tool_trace(kwargs["task_id"], {
            "action": "search", "ok": True, "capabilities": entries,
        })
        return "{}"

    monkeypatch.setattr(service, "dazah_tool", catalog)
    result = asyncio.run(service._try_basic_command_response(request))
    assert result is None
    assert queries == []


@pytest.mark.parametrize("stream", [False, True])
def test_endpoints_deliver_diagnostics_after_exhausted_repair(monkeypatch, stream):
    from fastapi.testclient import TestClient

    async def proxy_ok():
        return None

    async def no_skills(_request):
        return []

    async def no_memory(_request, message, _trace):
        return message

    async def catalog(**kwargs):
        platform.record_dazah_task_tool_trace(kwargs["task_id"], {
            "action": "search", "ok": True,
            "capabilities": [{"operation": "custom.read_records", "summary": "读取授权记录", "write": False}],
        })
        return "{}"

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            return {"final_response": "查询结果：custom.read_records，FAKE-001"}

    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    monkeypatch.setattr(service, "dazah_tool", catalog)
    monkeypatch.setattr(service, "_require_token", lambda _token: None)
    monkeypatch.setattr(service, "_check_dazah_llm_proxy", proxy_ok)
    monkeypatch.setattr(service, "_resolve_progressive_skills", no_skills)
    monkeypatch.setattr(service, "_finalize_user_memory", no_memory)
    request = payload()
    response = TestClient(service.app).post(
        "/v2/agent/runs" + ("/stream" if stream else ""), json=request.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert "FAKE-001" not in response.text
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert all(event["trace_id"] == str(request.trace_id) for event in events)
        answer = next(event["data"]["message"] for event in events if event["type"] == "finished")
    else:
        answer = response.json()["message"]
    assert "读取授权记录" in answer
    assert "已尝试一次只读修复" in answer
    assert str(request.trace_id) in answer


def test_capability_catalog_completes_request_without_business_execution(monkeypatch):
    request = payload()
    request.message = "你可以在质量模块中帮我做些什么"
    platform.register_dazah_task_context("capability-completion", request.context)
    platform.record_dazah_task_tool_trace("capability-completion", {
        "action": "search", "ok": True,
        "capabilities": [{"operation": "quality.list_deviations", "summary": "查询质量偏差列表", "write": False}],
    })

    class NoRepairAgent:
        def run_conversation(self, *_args, **_kwargs):
            pytest.fail("Authorized catalog already completes this capability question")

    try:
        result = service._repair_business_response(
            NoRepairAgent(), request, {"final_response": "Dazah 平台查询结果：quality.list_deviations"},
            task_id="capability-completion", history=[], cancellation=None,
        )
        assert "查询质量偏差列表" in result["final_response"]
        assert "尚未全部完成" not in result["final_response"]
        assert "没有取得" not in result["final_response"]
    finally:
        platform.unregister_dazah_task_context("capability-completion")


@pytest.mark.parametrize("repaired", [True, False])
def test_repair_reuses_real_read_results_without_repeating_execution(monkeypatch, repaired):
    """An unplanned run must retain its data even after the original model turn ends."""
    request = payload()
    task_id = "retained-read"
    operation = "custom.read_records"
    requests = []
    real_client = httpx.AsyncClient

    def respond(http_request):
        requests.append(http_request.url.path)
        if http_request.url.path.endswith("/search"):
            return httpx.Response(200, json={"ok": True, "data": [
                {"operation": operation, "summary": "读取记录", "write": False},
            ]})
        if http_request.method == "GET":
            return httpx.Response(200, json={"ok": True, "data": {
                "operation": operation, "write": False, "confirmation_required": False,
                "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            }})
        return httpx.Response(200, json={"ok": True, "data": {"ok": True, "data": {
            "items": [{"record_id": "REAL-001", "api_key": "synthetic-private-value"}], "total": 1,
        }}})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    platform.register_dazah_task_context(task_id, request.context)

    class RepairAgent:
        max_iterations = 30

        def run_conversation(self, _message, **kwargs):
            instruction = kwargs["conversation_history"][-1]["content"]
            assert "REAL-001" in instruction
            assert "input_schema" in instruction
            assert "synthetic-private-value" not in instruction
            assert "limit" in instruction
            return {"final_response": "查询结果：custom.read_records，REAL-001" if repaired else ""}

    try:
        asyncio.run(platform.dazah_tool("describe", operation=operation, task_id=task_id))
        asyncio.run(platform.dazah_tool("execute", operation=operation, params={"limit": 1}, task_id=task_id))
        result = service._repair_business_response(
            RepairAgent(), request, {"final_response": "查询结果：custom.unverified_records，FAKE-001"},
            task_id=task_id, history=[], cancellation=None,
        )
        assert "REAL-001" in result["final_response"]
        assert "FAKE-001" not in result["final_response"]
        assert "synthetic-private-value" not in result["final_response"]
        assert sum(path.endswith("/execute") for path in requests) == 1
        assert len(platform.current_dazah_task_evidence(task_id)) == 3
    finally:
        platform.unregister_dazah_task_context(task_id)
    assert platform.current_dazah_task_evidence(task_id) == []
