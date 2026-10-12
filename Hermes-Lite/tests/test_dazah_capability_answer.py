import asyncio
import json

import httpx
import pytest

from services import dazah_agent_service as service
from tools import dazah_platform as platform


QUESTION = "对于仓储管理模块你可以做些什么呢"
SCREENSHOT_QUESTION = "你可以在质量模块中帮我做些什么"
ENTRY = {
    "operation": "warehouse.list_page_records",
    "summary": "查询仓储页面记录",
    "write": False,
    "confirmation_required": False,
}
QUALITY_ENTRY = {**ENTRY, "operation": "quality.list_deviations", "summary": "查询质量偏差列表"}


@pytest.mark.parametrize("action", ["search", "describe"])
def test_catalog_calls_record_current_task_metadata(monkeypatch, action):
    real_client = httpx.AsyncClient
    data = [ENTRY] if action == "search" else ENTRY
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": data}))
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    platform.register_dazah_task_context("capability-test", {"user_id": "user-test", "tenant_id": "tenant-test"})
    try:
        asyncio.run(platform.dazah_tool(action, operation=ENTRY["operation"], task_id="capability-test"))
        trace = platform.current_dazah_task_tool_trace("capability-test")
        assert trace == [{"action": action, "ok": True, "capabilities": [ENTRY]}]
    finally:
        platform.unregister_dazah_task_context("capability-test")


def test_capability_answer_uses_catalog_without_claiming_records():
    answer = service._verified_agent_message(
        "Dazah 平台查询结果 warehouse.list_page_records：虚构记录 FAKE-001",
        [],
        [{"action": "search", "ok": True, "capabilities": [ENTRY]}],
        user_message=QUESTION,
    )
    assert ENTRY["summary"] in answer
    assert ENTRY["operation"] in answer
    assert "FAKE-001" not in answer
    assert "没有取得 Dazah" not in answer


@pytest.mark.parametrize("trace", [[], [{"action": "search", "ok": False, "capabilities": [ENTRY]}]])
def test_capability_answer_fails_closed_without_catalog(trace):
    answer = service._verified_agent_message("Dazah 平台 warehouse.list_page_records", [], trace, user_message=QUESTION)
    assert "未取得" in answer
    assert ENTRY["operation"] not in answer


def test_empty_catalog_is_not_reported_as_query_failure():
    answer = service._verified_agent_message(
        "invented", [], [{"action": "search", "ok": True, "capabilities": []}], user_message=QUESTION,
    )
    assert "未返回匹配" in answer
    assert "invented" not in answer


def test_capability_answer_keeps_write_confirmation_requirement():
    entry = {**ENTRY, "write": True, "confirmation_required": True}
    answer = service._verified_agent_message(
        "invented", [], [{"action": "describe", "ok": True, "capabilities": [entry]}], user_message=QUESTION,
    )
    assert "写入需确认" in answer


def test_catalog_evidence_never_authorizes_business_records():
    answer = service._verified_agent_message(
        "查询结果：Dazah 平台 warehouse.list_page_records，FAKE-001",
        [],
        [{"action": "search", "ok": True, "capabilities": [ENTRY]}],
        user_message="查询仓储记录",
    )
    assert "没有取得 Dazah" in answer
    assert "FAKE-001" not in answer


def test_capability_route_uses_dynamic_catalog():
    instruction = service._business_read_routing_instruction(QUESTION)
    assert "action='search'" in instruction
    assert "不得执行" in instruction
    assert "warehouse." not in instruction


@pytest.mark.parametrize("message", [
    "你可以帮我查询仓储记录吗", "你能做一份库存报告吗",
    "介绍仓储能力，再查询最近三条记录",
    "你有什么能力？请查询库存",
    "你有哪些功能，同时发送报告给我",
])
def test_business_requests_are_not_capability_questions(message):
    assert service._is_capability_question(message) is False


@pytest.mark.parametrize("question", [QUESTION, SCREENSHOT_QUESTION])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("outcome", ["available", "denied", "empty", "invalid_json"])
def test_run_endpoints_render_real_capability_catalog(monkeypatch, stream, outcome, question):
    import uuid

    from fastapi.testclient import TestClient
    expected_entry = QUALITY_ENTRY if question == SCREENSHOT_QUESTION else ENTRY

    async def no_proxy_error():
        return None

    async def no_plan(_payload):
        return None

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            task_id = kwargs["task_id"]
            try:
                asyncio.run(fake_catalog("search", query=question, task_id=task_id))
            except ValueError:
                platform.record_dazah_task_tool_trace(task_id, {
                    "action": "search", "ok": False, "error_code": "invalid_response",
                })
            return {"final_response": ""}

    async def no_skills(_payload):
        return []

    async def no_memory(_payload, message, _trace):
        return message

    async def fake_catalog(action, **kwargs):
        assert action == "search"
        assert kwargs["query"] in {question, ""}
        task_id = kwargs["task_id"]
        assert platform.current_dazah_request_context(task_id)["user_id"] == "user-test"
        if outcome == "invalid_json":
            raise ValueError("invalid upstream JSON")
        if outcome == "denied":
            platform.record_dazah_task_tool_trace(task_id, {
                "action": "search", "ok": False, "status_code": 403,
            })
            return json.dumps({"ok": False, "status_code": 403})
        entries = [expected_entry] if outcome == "available" else []
        platform.record_dazah_task_tool_trace(
            task_id, {"action": "search", "ok": True, "capabilities": entries},
        )
        return json.dumps({"data": entries})

    monkeypatch.setattr(service, "_require_token", lambda _token: None)
    monkeypatch.setattr(service, "_check_dazah_llm_proxy", no_proxy_error)
    monkeypatch.setattr(service, "_resolve_progressive_skills", no_skills)
    monkeypatch.setattr(service, "_finalize_user_memory", no_memory)
    monkeypatch.setattr(service, "dazah_tool", fake_catalog)
    monkeypatch.setattr(service, "_plan_business_task", no_plan)
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    request = {
        "protocol_version": "2.0",
        "run_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "session_id": "capability-session",
        "message": question,
        "subject": {"tenant_id": "tenant-test", "user_id": "user-test", "source": "web"},
        "source": {"platform": "web"},
    }
    previous_tasks = set(platform._task_request_contexts)
    response = TestClient(service.app).post("/v2/agent/runs" + ("/stream" if stream else ""), json=request)
    assert set(platform._task_request_contexts) == previous_tasks
    assert response.status_code == 200
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        answer = next(event["data"]["message"] for event in events if event["type"] == "finished")
    else:
        answer = response.json()["message"]
    if outcome == "available":
        assert expected_entry["summary"] in answer
        assert expected_entry["operation"] in answer
    elif outcome == "empty":
        assert "未返回匹配" in answer
        assert ENTRY["operation"] not in answer
    else:
        assert "尚未全部完成" in answer
        assert request["trace_id"] in answer
        assert ENTRY["operation"] not in answer
    assert "FAKE-001" not in answer
    assert "没有取得 Dazah" not in answer
    if outcome == "available":
        assert "尚未全部完成" not in answer
        assert "修复状态" not in answer


@pytest.mark.parametrize("message", [
    SCREENSHOT_QUESTION,
    "你可以在仓储模块中帮我做些什么",
    "在质量模块中，你能帮我处理哪些事情？",
    "你能帮我做什么质量管理工作",
    "采购管理方面可以请你提供哪些帮助",
    "生产模块里有哪些事情可以交给你处理",
])
def test_capability_questions_allow_domain_and_pronouns_between_intent_words(message):
    assert service._is_capability_question(message) is True


@pytest.mark.parametrize("message", [
    "你可以在质量模块中帮我查询最近三条偏差吗",
    "你可以在质量模块中帮我做些什么，然后查询最近三条偏差",
    "你可以在质量模块中帮我做些什么，查询最近三条偏差",
    "你能做些什么？请创建一条质量偏差",
])
def test_interleaved_capability_wording_keeps_concrete_execution_requests(message):
    assert service._is_capability_question(message) is False


@pytest.mark.parametrize("status", [403, 503])
def test_failed_catalog_calls_do_not_record_success(monkeypatch, status):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _request: httpx.Response(status, json={"data": [ENTRY]}))
    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    platform.register_dazah_task_context("capability-test", {"user_id": "user-test", "tenant_id": "tenant-test"})
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("search", task_id="capability-test")))
        assert result["ok"] is False
        assert not any(item.get("ok") is True for item in platform.current_dazah_task_tool_trace("capability-test"))
    finally:
        platform.unregister_dazah_task_context("capability-test")
