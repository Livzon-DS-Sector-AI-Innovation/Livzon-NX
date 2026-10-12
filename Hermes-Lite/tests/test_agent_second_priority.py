import asyncio
import json
import threading

import httpx
import pytest

from services import dazah_agent_service as service
from services.agent_task_contract import AgentTaskPlan, TaskEvidence, build_draft_evidence, evaluate_plan, render_task_reply
from services.capability_retrieval import select_capabilities
from services.task_recovery import recovery_decision
from tools import dazah_platform as platform


def fact(step="q", **kwargs):
    return TaskEvidence(id=f"e-{step}", step_id=step, occurred_at="2026-10-10T00:00:00Z", action="execute", **kwargs)


@pytest.mark.parametrize("code,write,category", [
    ("http_403", False, "stop"), ("http_401", False, "stop"),
    ("http_422", False, "parameters"), ("http_400", False, "parameters"),
    ("timeout", False, "transient"), ("http_503", False, "transient"),
    ("http_409", False, "stop"), ("http_404", False, "stop"),
    ("timeout", True, "check_receipt"), ("http_502", True, "check_receipt"), ("invalid_response", True, "check_receipt"),
])
def test_error_recovery_respects_type_and_write_uncertainty(code, write, category):
    assert recovery_decision([fact(ok=False, write=write, error_code=code)]).category == category


def test_empty_records_require_user_choice_but_zero_statistics_remain_valid():
    assert recovery_decision([fact(ok=True, write=False, data={"items": [], "total": 0})]).category == "ask_user"
    assert recovery_decision([fact(ok=True, write=False, data={"count": 0})]).category == "discover"


def test_analysis_reference_failure_is_not_reported_as_a_permission_or_business_rejection():
    decision = recovery_decision([fact(ok=False, write=False, error_code="analysis_unavailable")])
    assert "引用校验" in decision.instruction
    assert "能力停用" not in decision.instruction and "业务规则拒绝" not in decision.instruction


@pytest.mark.parametrize("response,expected", [
    ('{"operations":["custom.read"]}', ["custom.read"]),
    ('{"operations":["unauthorized.read"]}', []),
    ('{"operations":["custom.read","custom.read"]}', []),
    ('{"operations":["custom.read"],"user_id":"spoof"}', []),
    ('not JSON', []),
])
def test_semantic_selection_cannot_escape_live_directory(response, expected):
    async def llm(messages, task_name):
        assert task_name == "capability_selection"
        payload = json.loads(messages[-1]["content"])
        assert "input_schema" not in payload["directory"][0]
        return response

    assert asyncio.run(select_capabilities("找异常台账", [{"operation": "custom.read", "summary": "偏差记录", "input_schema": {}}], llm)) == expected


def test_semantic_provider_failure_preserves_fallback():
    async def llm(*_args):
        raise RuntimeError("provider unavailable")

    assert asyncio.run(select_capabilities("查询", [{"operation": "custom.read"}], llm)) == []


def install(monkeypatch, *, write=False, failure=None, data=None):
    original = httpx.AsyncClient
    requests = []

    def respond(req):
        requests.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"data": {"operation": "custom.perform", "write": write, "confirmation_required": write}})
        executions = [item for item in requests if item.url.path.endswith("/execute")]
        if len(executions) == 1 and failure is not None:
            if failure == "timeout":
                raise httpx.ReadTimeout("timed out", request=req)
            return httpx.Response(failure, json={"detail": "mock failure"})
        return httpx.Response(200, json={"data": {"ok": True, "data": data if data is not None else {"id": "R-1"}}})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    context = {"user_id": "test-user", "tenant_id": "test", "source": "web"}
    platform.register_dazah_task_context("recovery", context)
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "write" if write else "read", "goal": "处理记录"}]})
    platform.configure_dazah_task_plan("recovery", p)
    asyncio.run(platform.dazah_tool("describe", operation="custom.perform", task_id="recovery", step_id="q"))
    return requests, p


@pytest.mark.parametrize("failure", ["timeout", 429, 500, 502, 503, 504])
def test_read_temporary_failure_retries_exact_request_once(monkeypatch, failure):
    requests, p = install(monkeypatch, failure=failure)
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", params={"department_id": "D-1", "page": 2}, task_id="recovery", step_id="q")))
        assert result["data"]["ok"] is True
        assert len(requests) == 3
        assert requests[1].content == requests[2].content
        assert evaluate_plan(p, platform.current_dazah_task_evidence("recovery"))[0].state == "completed"
    finally:
        platform.unregister_dazah_task_context("recovery")


@pytest.mark.parametrize("failure", ["timeout", 500, 502, 503, 504])
def test_unknown_write_cannot_be_replayed_even_by_model(monkeypatch, failure):
    requests, p = install(monkeypatch, write=True, failure=failure)
    try:
        asyncio.run(platform.dazah_tool("execute", operation="custom.perform", task_id="recovery", step_id="q"))
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", task_id="recovery", step_id="q")))
        assert result["error"] == "write_execution_unknown"
        assert len(requests) == 2
        facts = platform.current_dazah_task_evidence("recovery")
        assert evaluate_plan(p, facts)[0].state == "execution_unknown"
        assert "执行回执" in render_task_reply(p, facts)
    finally:
        platform.unregister_dazah_task_context("recovery")


@pytest.mark.parametrize("failure", [400, 401, 403, 404, 409, 422])
def test_non_temporary_errors_are_not_transport_retried(monkeypatch, failure):
    requests, _ = install(monkeypatch, failure=failure)
    try:
        asyncio.run(platform.dazah_tool("execute", operation="custom.perform", task_id="recovery", step_id="q"))
        assert len(requests) == 2
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_empty_query_cannot_silently_expand_filters(monkeypatch):
    requests, _ = install(monkeypatch, data={"items": [], "total": 0})
    try:
        asyncio.run(platform.dazah_tool("execute", operation="custom.perform", params={"status": "open"}, task_id="recovery", step_id="q"))
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", params={}, task_id="recovery", step_id="q")))
        assert result["error"] == "empty_result_requires_user_choice"
        assert len(requests) == 2
    finally:
        platform.unregister_dazah_task_context("recovery")


def closed_loop_plan():
    return AgentTaskPlan.model_validate({"steps": [
        {"id": "q", "kind": "read", "goal": "定位记录"},
        {"id": "d", "kind": "draft", "goal": "处理草稿", "depends_on": ["q"]},
        {"id": "w", "kind": "write", "goal": "确认后保存", "depends_on": ["d"]},
        {"id": "v", "kind": "verify", "goal": "核对保存结果", "depends_on": ["w"], "verification_checks": [
            {"source_step_id": "w", "source_pointer": "/id", "result_pointer": "/id"},
            {"source_step_id": "w", "source_pointer": "/status", "result_pointer": "/status"},
        ]},
    ]})


@pytest.mark.parametrize("verification,state", [
    ({"id": "R-1", "status": "draft"}, "completed"),
    ({"id": "R-2", "status": "draft"}, "failed"),
    ({"id": "R-1"}, "failed"),
])
def test_query_draft_write_and_receipt_verification_are_distinct(verification, state):
    p = closed_loop_plan()
    facts = [fact(ok=True, write=False, data={"id": "R-1", "issue": "实际问题"})]
    drafts = build_draft_evidence(p, facts)
    assert len(drafts) == 1 and drafts[0].data["依据"][0]["evidence_id"] == "e-q"
    assert "未写入业务系统" in drafts[0].data["状态"]
    facts += drafts
    assert not build_draft_evidence(p, facts)
    assert [item.state for item in evaluate_plan(p, facts)] == ["completed", "completed", "not_started", "blocked"]
    pending = facts + [fact("w", ok=True, write=True, confirmation_id="C-1")]
    assert [item.state for item in evaluate_plan(p, pending)][-2:] == ["awaiting_confirmation", "blocked"]
    done = facts + [fact("w", ok=True, write=True, data={"id": "R-1", "status": "draft"}), fact("v", ok=True, write=False, data=verification)]
    assert evaluate_plan(p, done)[-1].state == state
    if state == "failed":
        assert "核对未通过" in render_task_reply(p, done)


def test_verification_without_criteria_never_claims_verified():
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "verify", "goal": "核对"}]})
    assert evaluate_plan(p, [fact(ok=True, write=False, data={"id": "R-1"})])[0].state == "verification_pending"


def test_cancelled_read_is_not_retried(monkeypatch):
    requests, _ = install(monkeypatch, failure="timeout")
    cancelled = threading.Event()
    cancelled.set()
    platform._task_request_contexts["recovery"]["_cancellation_event"] = cancelled
    try:
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", task_id="recovery", step_id="q")))
        assert result["error"] == "run_cancelled"
        assert len(requests) == 1
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_parameter_repair_only_changes_reported_fields(monkeypatch):
    requests, _ = install(monkeypatch)
    platform._task_request_contexts["recovery"]["_parameter_failures"] = {"q": {
        "operation": "custom.perform", "input": {"page": "bad", "department_id": "D-1"}, "fields": ["page"],
    }}
    platform.enable_dazah_task_read_only_repair("recovery")
    try:
        denied = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", params={"page": 1}, task_id="recovery", step_id="q")))
        assert denied["error"] == "parameter_repair_requires_user_input"
        corrected = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.perform", params={"page": 1, "department_id": "D-1"}, task_id="recovery", step_id="q")))
        assert corrected["data"]["ok"] is True
        assert len(requests) == 2
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_parameter_errors_retain_field_names_without_values(monkeypatch):
    from services.task_recovery import validation_fields

    assert validation_fields({"detail": "page: invalid sensitive-value"}) == ["page"]
    assert validation_fields({"detail": [{"loc": ["body", "record_id"], "input": "private"}]}) == ["record_id"]
    assert validation_fields({"detail": "internal failure"}) == []


def test_platform_validation_envelope_is_repairable_even_with_http_200(monkeypatch):
    original = httpx.AsyncClient

    def respond(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": {"operation": "custom.read", "write": False}})
        return httpx.Response(200, json={"data": {"ok": False, "data": {"message": "page: invalid"}, "meta": {"validation": "failed"}}})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    platform.register_dazah_task_context("recovery", {"user_id": "test-user", "tenant_id": "test", "source": "web"})
    try:
        for action in ["describe", "execute"]:
            asyncio.run(platform.dazah_tool(action, operation="custom.read", params={"page": "bad"}, task_id="recovery", step_id="q"))
        facts = platform.current_dazah_task_evidence("recovery")
        assert recovery_decision(facts).category == "parameters"
        assert facts[-1].error_fields == ["page"]
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_gateway_materializes_draft_before_dependent_write(monkeypatch):
    requests, _ = install(monkeypatch)
    p = closed_loop_plan()
    platform.configure_dazah_task_plan("recovery", p)
    try:
        asyncio.run(platform.dazah_tool("execute", operation="custom.perform", task_id="recovery", step_id="q"))
        asyncio.run(platform.dazah_tool("search", task_id="recovery", step_id="w"))
        facts = platform.current_dazah_task_evidence("recovery")
        assert any(item.step_id == "d" and item.action == "draft" for item in facts)
        assert evaluate_plan(p, facts)[1].state == "completed"
        assert all(not item.write for item in facts if item.ok and item.action in {"execute", "draft"})
        assert len(requests) == 3
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_planned_repair_semantically_selects_only_authorized_empty_search_fallback(monkeypatch):
    import uuid

    monkeypatch.setenv("AGENT_LLM_PROXY_TOKEN", "test-token")
    payload = service.AgentBackendV2Request(
        protocol_version="2.0", run_id=uuid.uuid4(), trace_id=uuid.uuid4(), session_id="recovery-test",
        message="找异常台账", subject={"tenant_id": "test", "user_id": "test-user", "source": "web"}, source={"platform": "web"},
    )
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "查异常", "search_query": "异常"}]})
    calls = []

    async def directory(**kwargs):
        calls.append(kwargs)
        entries = [] if kwargs["query"] else [{"operation": "custom.read", "summary": "质量事件", "write": False}]
        platform._retain_task_evidence("recovery", "q", "search", None, ok=True, data=entries)
        return json.dumps({"data": entries})

    async def llm(messages, _task):
        assert "custom.read" in messages[-1]["content"]
        return '{"operations":["custom.read"]}'

    class Agent:
        max_iterations = 30

        def run_conversation(self, _message, **kwargs):
            assert '"q": ["custom.read"]' in kwargs["system_message"]
            assert "tool_results" in kwargs["system_message"]
            return {"final_response": "未执行"}

    monkeypatch.setattr(service, "dazah_tool", directory)
    monkeypatch.setattr(service, "_call_memory_llm", llm)
    platform.register_dazah_task_context("recovery", {})
    platform.configure_dazah_task_plan("recovery", p)
    try:
        service._repair_planned_steps(Agent(), p, payload, task_id="recovery", history=[], cancellation=None)
        assert [call["query"] for call in calls] == ["异常", ""]
        assert evaluate_plan(p, platform.current_dazah_task_evidence("recovery"))[0].state == "not_started"
    finally:
        platform.unregister_dazah_task_context("recovery")


def test_runtime_query_draft_write_verify_reply_uses_actual_receipts(monkeypatch):
    import uuid

    p = closed_loop_plan()
    original = httpx.AsyncClient
    executions = []

    def respond(req):
        if req.method == "GET":
            operation = req.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"data": {"operation": operation, "write": operation == "custom.save", "confirmation_required": False}})
        executions.append(json.loads(req.content))
        return httpx.Response(200, json={"data": {"ok": True, "data": {"id": "REAL-1", "status": "draft"}}})

    async def planner(_request):
        return p

    class Agent:
        max_iterations = 30

        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            for step_id, operation in [("q", "custom.read"), ("w", "custom.save"), ("v", "custom.read")]:
                for action in ["describe", "execute"]:
                    asyncio.run(platform.dazah_tool(action, operation=operation, task_id=kwargs["task_id"], step_id=step_id))
            return {"final_response": "FAKE-001 已完成核对"}

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(service, "_plan_business_task", planner)
    monkeypatch.setattr(service, "DazahAIAgent", Agent)
    payload = service.AgentBackendV2Request(
        protocol_version="2.0", run_id=uuid.uuid4(), trace_id=uuid.uuid4(), session_id="loop-test",
        message="查询后形成草稿，按平台允许的方式保存，再核对结果",
        subject={"tenant_id": "test", "user_id": "test-user", "source": "web"}, source={"platform": "web"},
    )
    _, result = service._run_agent_conversation(payload)
    assert "REAL-1" in result["final_response"] and "FAKE-001" not in result["final_response"]
    states = next(item["steps"] for item in result["tool_trace"] if item["action"] == "task_outcome")
    assert all(item["state"] == "completed" for item in states)
    assert "来源：" not in result["final_response"] and "任务：" not in result["final_response"]
    assert len(executions) == 3
    assert [item["execution_context"]["task_step_id"] for item in executions] == ["q", "w", "v"]
