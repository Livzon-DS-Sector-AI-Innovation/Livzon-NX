import asyncio
import json
import threading
import uuid

import httpx
import pytest
from pydantic import ValidationError

from services import dazah_agent_service as service
from services.agent_task_contract import AgentTaskPlan, TaskEvidence, evaluate_plan, render_task_reply
from tools import dazah_platform as platform


def plan():
    return AgentTaskPlan.model_validate({"steps": [
        {"id": "intro", "kind": "capability", "goal": "介绍质量能力", "search_query": "质量"},
        {"id": "query", "kind": "read", "goal": "查询偏差", "search_query": "偏差"},
        {"id": "send", "kind": "write", "goal": "发送查询结果", "depends_on": ["query"]},
    ]})


def evidence(step, action, **kwargs):
    return TaskEvidence(id=uuid.uuid4().hex, step_id=step, action=action, ok=True,
                        occurred_at="2026-10-10T00:00:00+00:00", **kwargs)


def request():
    return service.AgentBackendV2Request(
        protocol_version="2.0", run_id=uuid.uuid4(), trace_id=uuid.uuid4(), session_id="task-test",
        message="先介绍质量能力，查询最近三条偏差，再发送给我",
        subject={"tenant_id": "test", "user_id": "test-user", "source": "web"}, source={"platform": "web"},
    )


@pytest.mark.parametrize("steps", [
    [], [{"id": "a", "kind": "invalid", "goal": "x"}],
    [{"id": "a", "kind": "read", "goal": "x", "user_id": "spoof"}],
    [{"id": "a", "kind": "read", "goal": "x", "depends_on": ["b"]}],
    [{"id": "a", "kind": "read", "goal": "x"}, {"id": "a", "kind": "read", "goal": "y"}],
])
def test_invalid_or_authority_bearing_plans_are_rejected(steps):
    with pytest.raises(ValidationError):
        AgentTaskPlan.model_validate({"steps": steps})


def test_success_of_one_task_never_completes_other_tasks():
    facts = [evidence("intro", "search", data=[])]
    assert [item.state for item in evaluate_plan(plan(), facts)] == ["completed", "not_started", "blocked"]


def test_pending_write_is_not_execution_success():
    facts = [evidence("intro", "search", data=[]),
             evidence("query", "execute", operation="custom.read_records", write=False, data={"items": []}),
             evidence("send", "execute", operation="custom.send_records", write=True, confirmation_id="pending-test")]
    assert [item.state for item in evaluate_plan(plan(), facts)] == ["completed", "completed", "awaiting_confirmation"]
    assert "待确认，尚未执行" in render_task_reply(plan(), facts)


def test_corrected_write_confirmation_does_not_repeat_old_parameter_errors():
    p = AgentTaskPlan.model_validate({"steps": [{"id": "create", "kind": "write", "goal": "创建草稿"}]})
    facts = [TaskEvidence(id="invalid", step_id="create", action="execute", ok=False,
                          write=True, error_code="http_422", error_fields=["items.0.product_name"],
                          occurred_at="2026-10-10T00:00:00+00:00"),
             evidence("create", "execute", write=True, confirmation_id="pending-test")]
    reply = render_task_reply(p, facts)
    assert "待确认，尚未执行" in reply
    assert "需检查字段" not in reply
    assert "重新describe" not in reply


def test_pending_confirmation_does_not_hide_uncertain_write_receipt():
    p = AgentTaskPlan.model_validate({"steps": [{"id": "create", "kind": "write", "goal": "创建草稿"}]})
    facts = [TaskEvidence(id="unknown", step_id="create", action="execute", ok=False,
                          write=True, error_code="timeout", occurred_at="2026-10-10T00:00:00+00:00"),
             evidence("create", "execute", write=True, confirmation_id="pending-test")]
    assert "写入结果未知；禁止重发" in render_task_reply(p, facts)


def test_wrong_kind_null_result_and_missing_inputs_cannot_complete_read():
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "query"}]})
    assert evaluate_plan(p, [evidence("q", "execute", write=True, data={"count": 10})])[0].state == "not_started"
    assert evaluate_plan(p, [evidence("q", "execute", write=False)])[0].state == "not_started"
    p.steps[0].missing_inputs = ["日期范围"]
    assert evaluate_plan(p, [evidence("q", "execute", write=False, data={"count": 10})])[0].state == "blocked"
    assert "日期范围" in render_task_reply(p, [])


@pytest.mark.parametrize("failure", [ValueError("invalid output"), TimeoutError("timeout"),
                                     RuntimeError("no config"), RuntimeError("rate limit"), RuntimeError("provider error")])
def test_planner_failures_use_existing_safe_execution_fallback(monkeypatch, failure):
    monkeypatch.setenv("AGENT_LLM_PROXY_TOKEN", "test-token")

    async def fake_llm(*_args):
        raise failure

    monkeypatch.setattr(service, "_call_memory_llm", fake_llm)
    assert asyncio.run(service._plan_business_task(request())) is None


def test_planner_schema_and_proxy_adapter_are_used(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROXY_TOKEN", "test-token")
    seen = []

    async def fake_llm(messages, task_name):
        seen.append((messages, task_name))
        return plan().model_dump_json()

    monkeypatch.setattr(service, "_call_memory_llm", fake_llm)
    result = asyncio.run(service._plan_business_task(request()))
    assert [step.kind for step in result.steps] == ["capability", "read", "write"]
    assert seen[0][1] == "agent_task_plan"
    assert "Schema" in seen[0][0][0]["content"]
    assert "可选筛选条件未提供不算缺失输入" in seen[0][0][0]["content"]
    assert "前置任务可提供的信息只放入depends_on" in seen[0][0][0]["content"]
    assert "不能作为write的knowledge前置依赖" in seen[0][0][0]["content"]


def install_transport(monkeypatch):
    original = httpx.AsyncClient
    seen = []

    def respond(req):
        seen.append(req)
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": [{"operation": "custom.read_records", "summary": "读取记录", "write": False}]})
        if req.method == "GET":
            write = "send_records" in req.url.path
            return httpx.Response(200, json={"data": {"operation": "custom.send_records" if write else "custom.read_records",
                                                      "write": write, "confirmation_required": write,
                                                      "output_hint": "只查询本地缓存，不代表外部实时数据"}})
        body = json.loads(req.content)
        if body["operation"] == "custom.send_records":
            return httpx.Response(200, json={"data": {"ok": True, "requires_confirmation": True,
                "confirmation": {"id": "pending-test", "status": "pending",
                    "operation": "custom.send_records", "summary": "发送查询记录",
                    "risk_level": "medium", "expires_at": "2026-10-10T12:00:00Z"}}})
        return httpx.Response(200, json={"data": {"ok": True, "data": {
            "items": [{"code": f"REAL-{i}"} for i in range(5)], "total": 5,
            "api_key": "credential-must-not-leak", "count": 7}}})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    return seen


def test_gateway_binds_dependencies_kind_and_evidence(monkeypatch):
    seen = install_transport(monkeypatch)
    platform.register_dazah_task_context("planned", request().context)
    platform.configure_dazah_task_plan("planned", plan())
    try:
        blocked = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.send_records", task_id="planned", step_id="send")))
        assert blocked["error"] == "step_dependencies_or_inputs_missing"
        assert not seen
        no_step = json.loads(asyncio.run(platform.dazah_tool("search", task_id="planned")))
        assert no_step["error"] == "valid_step_id_required"
        for action in ["describe", "execute"]:
            asyncio.run(platform.dazah_tool(action, operation="custom.read_records", params={"page": 1}, task_id="planned", step_id="query"))
        for action in ["describe", "execute"]:
            asyncio.run(platform.dazah_tool(action, operation="custom.send_records", task_id="planned", step_id="send"))
        facts = platform.current_dazah_task_evidence("planned")
        assert all(item.output_hint == "只查询本地缓存，不代表外部实时数据" for item in facts if item.action == "execute" and item.ok)
        assert next(item for item in facts if item.error_code == "step_dependencies_or_inputs_missing").output_hint is None
        assert [item.state for item in evaluate_plan(plan(), facts)] == ["not_started", "completed", "awaiting_confirmation"]
        reply = render_task_reply(plan(), facts)
        assert "REAL-0" in reply and "REAL-4" not in reply
        assert "credential-must-not-leak" not in reply
        assert "数量：7" in reply
        assert "查询条件：" not in reply and '"page": 1' not in reply
        assert "来源：" not in reply
        assert all(item.id not in reply for item in facts)
        assert all(item.id for item in facts if item.action == "execute" and item.ok)
        requests = [json.loads(req.content) for req in seen if req.url.path.endswith("/execute")]
        assert all(body["execution_context"]["evidence_id"] in {item.id for item in facts} for body in requests)
        assert [body["execution_context"]["task_step_id"] for body in requests] == ["query", "send"]
        public_trace = json.dumps(platform.current_dazah_task_tool_trace("planned"))
        assert "REAL-0" not in public_trace and "credential-must-not-leak" not in public_trace
    finally:
        platform.unregister_dazah_task_context("planned")
    assert platform.current_dazah_task_evidence("planned") == []


def test_read_outcome_diagnostics_keep_filter_names_without_values(monkeypatch, caplog):
    import logging

    install_transport(monkeypatch)
    platform.register_dazah_task_context("diagnostics", request().context)
    try:
        asyncio.run(platform.dazah_tool("describe", operation="custom.read_records", task_id="diagnostics"))
        with caplog.at_level(logging.INFO, logger="tools.dazah_platform"):
            asyncio.run(platform.dazah_tool("execute", operation="custom.read_records",
                params={"keyword": "synthetic-private-filter"}, task_id="diagnostics"))
        log = "\n".join(record.getMessage() for record in caplog.records)
        assert "Read query outcome" in log and "keyword" in log and "reported_total=5" in log
        assert "synthetic-private-filter" not in log and "REAL-0" not in log
    finally:
        platform.unregister_dazah_task_context("diagnostics")


def test_runtime_renders_actual_values_and_each_subtask_state(monkeypatch):
    install_transport(monkeypatch)

    async def fake_plan(_payload):
        return plan()

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            assert "step_id" in kwargs["system_message"]
            asyncio.run(platform.dazah_tool("search", query="quality", task_id=kwargs["task_id"], step_id="intro"))
            for action in ["describe", "execute"]:
                asyncio.run(platform.dazah_tool(action, operation="custom.read_records", params={"page": 1}, task_id=kwargs["task_id"], step_id="query"))
            for action in ["describe", "execute"]:
                asyncio.run(platform.dazah_tool(action, operation="custom.send_records", task_id=kwargs["task_id"], step_id="send"))
            return {"final_response": "全部完成，共999条记录，FAKE-001，已发送。"}

    monkeypatch.setattr(service, "_plan_business_task", fake_plan)
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    _, result = service._run_agent_conversation(request())
    reply = result["final_response"]
    assert "能力介绍" not in reply and "任务：" not in reply
    assert "来源：" not in reply and "查询条件：" not in reply
    assert "发送查询结果：待确认，尚未执行" in reply
    assert "FAKE-001" not in reply and "共999条记录" not in reply and "已发送" not in reply
    assert "REAL-0" in reply and "credential-must-not-leak" not in reply
    assert any(item["action"] == "task_outcome" for item in result["tool_trace"])


def test_step_kind_mismatch_cannot_reach_backend(monkeypatch):
    seen = install_transport(monkeypatch)
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "查询"}]})
    platform.register_dazah_task_context("planned", request().context)
    platform.configure_dazah_task_plan("planned", p)
    try:
        asyncio.run(platform.dazah_tool("describe", operation="custom.send_records", task_id="planned", step_id="q"))
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="custom.send_records", task_id="planned", step_id="q")))
        assert result["error"] == "step_operation_kind_mismatch"
        assert len(seen) == 1
        assert evaluate_plan(p, platform.current_dazah_task_evidence("planned"))[0].state == "failed"
    finally:
        platform.unregister_dazah_task_context("planned")


def test_planned_repair_completes_capability_without_executing(monkeypatch):
    install_transport(monkeypatch)
    p = AgentTaskPlan.model_validate({"steps": [{"id": "c", "kind": "capability", "goal": "介绍", "search_query": "质量"}]})
    platform.register_dazah_task_context("planned", request().context)
    platform.configure_dazah_task_plan("planned", p)
    try:
        service._repair_planned_steps(object(), p, request(), task_id="planned", history=[], cancellation=None)
        assert evaluate_plan(p, platform.current_dazah_task_evidence("planned"))[0].state == "completed"
        assert not any(item.action == "execute" for item in platform.current_dazah_task_evidence("planned"))
    finally:
        platform.unregister_dazah_task_context("planned")


@pytest.mark.parametrize("interrupt", ["denied", "cancelled"])
def test_planned_repair_stops_after_search_permission_or_cancellation(monkeypatch, interrupt):
    cancellation = threading.Event()
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "查询"}]})
    calls = []

    async def interrupted_search(**kwargs):
        calls.append(kwargs)
        if interrupt == "denied":
            platform.record_dazah_task_tool_trace("planned", {"action": "search", "status_code": 403})
        else:
            cancellation.set()
        return "{}"

    class NeverRun:
        def run_conversation(self, *_args, **_kwargs):
            pytest.fail("denied or cancelled runs must not invoke repair model")

    monkeypatch.setattr(service, "dazah_tool", interrupted_search)
    platform.register_dazah_task_context("planned", request().context)
    platform.configure_dazah_task_plan("planned", p)
    try:
        service._repair_planned_steps(NeverRun(), p, request(), task_id="planned", history=[], cancellation=cancellation)
        assert len(calls) == 1
        assert evaluate_plan(p, platform.current_dazah_task_evidence("planned"))[0].state == "not_started"
    finally:
        platform.unregister_dazah_task_context("planned")


def test_planned_repair_uses_live_description_and_preserves_iteration_limit(monkeypatch):
    seen = install_transport(monkeypatch)
    p = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "查询"}]})

    class RepairAgent:
        max_iterations = 30

        def run_conversation(self, _message, **kwargs):
            assert self.max_iterations == 4
            for action in ["describe", "execute"]:
                asyncio.run(platform.dazah_tool(action, operation="custom.read_records", task_id=kwargs["task_id"], step_id="q"))
            return {"final_response": "FAKE-001"}

    agent = RepairAgent()
    platform.register_dazah_task_context("planned", request().context)
    platform.configure_dazah_task_plan("planned", p)
    try:
        service._repair_planned_steps(agent, p, request(), task_id="planned", history=[], cancellation=None)
        assert agent.max_iterations == 30
        assert len(seen) == 3
        assert evaluate_plan(p, platform.current_dazah_task_evidence("planned"))[0].state == "completed"
        assert "FAKE-001" not in render_task_reply(p, platform.current_dazah_task_evidence("planned"))
    finally:
        platform.unregister_dazah_task_context("planned")


@pytest.mark.parametrize("stream", [False, True])
def test_endpoints_preserve_structured_results_and_confirmation_states(monkeypatch, stream):
    from fastapi.testclient import TestClient

    install_transport(monkeypatch)

    async def proxy_ok():
        return None

    async def no_skills(_request):
        return []

    async def fake_plan(_request):
        return plan()

    async def no_memory(_request, message, _trace):
        return message

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            for action in ["describe", "execute"]:
                asyncio.run(platform.dazah_tool(action, operation="custom.read_records", task_id=kwargs["task_id"], step_id="query"))
            for action in ["describe", "execute"]:
                asyncio.run(platform.dazah_tool(action, operation="custom.send_records", task_id=kwargs["task_id"], step_id="send"))
            return {"final_response": "FAKE-001，已发送999条。"}

    monkeypatch.setattr(service, "_require_token", lambda _token: None)
    monkeypatch.setattr(service, "_check_dazah_llm_proxy", proxy_ok)
    monkeypatch.setattr(service, "_resolve_progressive_skills", no_skills)
    monkeypatch.setattr(service, "_plan_business_task", fake_plan)
    monkeypatch.setattr(service, "_finalize_user_memory", no_memory)
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    response = TestClient(service.app).post("/v2/agent/runs" + ("/stream" if stream else ""), json=request().model_dump(mode="json"))
    assert response.status_code == 200
    assert "FAKE-001" not in response.text and "credential-must-not-leak" not in response.text
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        result = next(event["data"] for event in events if event["type"] == "finished")
    else:
        result = response.json()
    assert "任务：" not in result["message"] and "query：" not in result["message"]
    assert "来源：" not in result["message"] and "查询条件：" not in result["message"]
    assert "发送查询结果：待确认，尚未执行" in result["message"]
    assert "REAL-0" in result["message"]
    assert result["pending_confirmations"][0]["id"] == "pending-test"
