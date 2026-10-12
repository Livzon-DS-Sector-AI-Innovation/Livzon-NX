import asyncio
import json

import pytest
import httpx

from services.agent_task_contract import AgentTaskPlan, TaskEvidence, build_draft_evidence, evaluate_plan
from services.grounded_analysis import build_analysis_evidence


def plan():
    return AgentTaskPlan.model_validate(
        {
            "steps": [
                {"id": "read", "kind": "knowledge", "goal": "按问题跨模块获取依据"},
                {"id": "analyze", "kind": "analysis", "goal": "分析业务事实", "depends_on": ["read"]},
                {"id": "report", "kind": "draft", "goal": "形成审核报告", "depends_on": ["analyze"]},
            ]
        }
    )


def fact():
    return TaskEvidence(
        id="source",
        step_id="read",
        action="execute",
        operation="custom.read",
        ok=True,
        write=False,
        occurred_at="2026-10-10T00:00:00Z",
        data={"count": 4},
        filters={"year": 2026},
    )


def test_query_success_does_not_complete_analysis_or_report():
    assert [item.state for item in evaluate_plan(plan(), [fact()])] == ["completed", "not_started", "blocked"]


def test_analysis_prompt_defines_citation_id_and_data_pointer_root():
    async def model(messages, _task_name):
        instruction = messages[0]["content"]
        assert "不能使用step_id或operation" in instruction
        assert "不要加/data前缀" in instruction
        assert "空字符串引用整个data" in instruction
        payload = json.loads(messages[1]["content"])
        assert payload["citation_choices"] == [{"evidence_id": "source", "pointers": ["", "/count"]}]
        return json.dumps({"findings": [{"explanation": "有4条记录", "evidence_id": "source", "pointer": "/count"}], "limitations": ["仅依据本轮资料"]})

    result = asyncio.run(build_analysis_evidence(plan(), [fact()], model))
    assert result[0].ok
    assert result[0].data["分析"][0]["原始事实"] == 4


@pytest.mark.parametrize("bad_reference", ["id", "pointer"])
def test_analysis_repairs_invalid_reference_once_using_the_same_facts(bad_reference):
    calls = []

    async def model(messages, _task_name):
        calls.append(messages)
        if len(calls) == 2:
            assert "citation_" in messages[0]["content"]
            assert json.loads(messages[1]["content"])["evidence"][0]["id"] == "source"
        result = {"findings": [{"explanation": "仅凭人数不能核实同步完整性", "evidence_id": "source",
                                "pointer": "/count"}], "limitations": ["缺少同步状态和对照总数"]}
        if len(calls) == 1:
            result["findings"][0]["evidence_id" if bad_reference == "id" else "pointer"] = (
                "step-id" if bad_reference == "id" else "/data/count"
            )
        return "```json\n" + json.dumps(result, ensure_ascii=False) + "\n```"

    additions = asyncio.run(build_analysis_evidence(plan(), [fact()], model))
    assert len(calls) == 2 and len(additions) == 1 and additions[0].ok
    assert additions[0].data["分析"][0]["原始事实"] == 4


def test_completed_read_does_not_display_a_prior_failure_recovery_instruction():
    from services.agent_task_contract import render_task_reply
    task = AgentTaskPlan.model_validate({"steps": [{"id": "read", "kind": "read", "goal": "查询"}]})
    failed = fact().model_copy(update={"id": "failure", "ok": False, "data": None, "error_code": "execution_rejected"})
    reply = render_task_reply(task, [failed, fact()])
    assert "数量：4" in reply and '"count"' not in reply
    assert evaluate_plan(task, [failed, fact()])[0].state == "completed"
    assert "能力停用" not in reply


def test_citation_choices_escape_keys_and_exclude_nulls():
    from services.grounded_analysis import _citation_pointers
    choices = _citation_pointers({"a/b~c": [None, {"value": 0}]})
    assert "/a~1b~0c/0" not in choices
    assert "/a~1b~0c/1/value" in choices
    assert len(_citation_pointers(list(range(1000)))) == 256


def test_knowledge_index_cannot_complete_a_knowledge_answer():
    index = fact().model_copy(update={"result_kind": "knowledge_index"})
    assert evaluate_plan(plan(), [index])[0].state == "not_started"

    async def model(*_args):
        pytest.fail("an index cannot stand in for source knowledge")

    assert asyncio.run(build_analysis_evidence(plan(), [index], model)) == []


def test_ending_read_repair_keeps_uncertain_write_guard():
    from tools import dazah_platform as platform
    platform.register_dazah_task_context("repair-lifecycle", {"_uncertain_writes": {"custom.write"}})
    try:
        platform.enable_dazah_task_read_only_repair("repair-lifecycle")
        assert platform.current_dazah_request_context("repair-lifecycle")["_read_only_repair"]
        platform.finish_dazah_task_read_only_repair("repair-lifecycle")
        context = platform.current_dazah_request_context("repair-lifecycle")
        assert "_read_only_repair" not in context and "_repair_calls_remaining" not in context
        assert context["_uncertain_writes"] == {"custom.write"}
    finally:
        platform.unregister_dazah_task_context("repair-lifecycle")


def test_runtime_discovers_cross_module_facts_and_produces_a_cited_review_report(monkeypatch):
    from services import dazah_agent_service as service
    from tools import dazah_platform as platform
    from uuid import uuid4

    task_plan = AgentTaskPlan.model_validate(
        {
            "steps": [
                {"id": "people", "kind": "knowledge", "goal": "读取人事业务依据"},
                {"id": "stock", "kind": "read", "goal": "读取仓储事实"},
                {"id": "analyze", "kind": "analysis", "goal": "分析跨模块事实", "depends_on": ["people", "stock"]},
                {"id": "report", "kind": "draft", "goal": "业务报告", "depends_on": ["analyze"]},
            ]
        }
    )

    async def planner(_payload):
        return task_plan

    original = httpx.AsyncClient
    executions = []

    def respond(req):
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": [{"operation": "custom.read", "write": False}]})
        if req.method == "GET":
            return httpx.Response(
                200,
                json={"data": {"operation": req.url.path.rsplit("/", 1)[-1], "write": False, "result_kind": "records"}},
            )
        operation = json.loads(req.content)["operation"]
        executions.append(operation)
        return httpx.Response(200, json={"data": {"ok": True, "data": {"count": 4}}})

    class FakeAgent:
        max_iterations = 30

        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            assert "不得把知识来源固定为某个模块" in kwargs["system_message"]
            for step, operation in [("people", "hr.custom_facts"), ("stock", "warehouse.custom_facts")]:
                for action in ["search", "describe", "execute"]:
                    asyncio.run(
                        platform.dazah_tool(
                            action, operation=operation, query=step, task_id=kwargs["task_id"], step_id=step
                        )
                    )
            return {"final_response": "不可信的任务完成声明"}

    async def model(messages, _purpose):
        sources = json.loads(messages[1]["content"])["evidence"]
        assert {source["operation"] for source in sources} == {"hr.custom_facts", "warehouse.custom_facts"}
        return json.dumps(
            {
                "findings": [
                    {"explanation": "本轮两个来源各返回4", "evidence_id": source["id"], "pointer": "/count"}
                    for source in sources
                ],
                "limitations": ["辅助分析，仅在本轮查询范围内有效"],
            }
        )

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-only")
    monkeypatch.setattr(
        platform.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )
    monkeypatch.setattr(service, "_plan_business_task", planner)
    monkeypatch.setattr(service, "_call_memory_llm", model)
    monkeypatch.setattr(service, "DazahAIAgent", FakeAgent)
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid4(),
        trace_id=uuid4(),
        session_id="test",
        message="根据问题读取业务事实，分析并形成报告",
        subject={"user_id": "user", "tenant_id": "tenant", "source": "web"},
        source={"platform": "web"},
    )
    _, result = service._run_agent_conversation(payload)
    reply = result["final_response"]
    states = next(item["steps"] for item in result["tool_trace"] if item["action"] == "task_outcome")
    assert all(item["state"] == "completed" for item in states)
    assert "来源：" not in reply and "任务：" not in reply
    assert "仅供审核，未写入业务系统" in reply
    assert "hr.custom_facts" not in reply and "warehouse.custom_facts" not in reply
    assert "原始事实" in reply and "4" in reply
    assert "不可信的任务完成声明" not in reply
    assert executions == ["hr.custom_facts", "warehouse.custom_facts"]


def test_cited_analysis_and_report_use_current_run_sources():
    async def model(messages, purpose):
        assert purpose == "agent_grounded_analysis"
        assert json.loads(messages[1]["content"])["evidence"][0]["operation"] == "custom.read"
        return json.dumps(
            {
                "findings": [{"explanation": "工具统计为4", "evidence_id": "source", "pointer": "/count"}],
                "limitations": ["仅在查询条件内有效"],
            }
        )

    evidence = [fact()]
    evidence += asyncio.run(build_analysis_evidence(plan(), evidence, model))
    evidence += build_draft_evidence(plan(), evidence)
    assert [item.state for item in evaluate_plan(plan(), evidence)] == ["completed"] * 3
    finding = evidence[1].data["分析"][0]
    assert finding["原始事实"] == 4 and finding["operation"] == "custom.read"
    assert evidence[2].data["依据"][0]["evidence_id"] == evidence[1].id
    assert evidence[2].data["状态"] == "仅供审核，未写入业务系统"
    from services.agent_task_contract import render_task_reply

    reply = render_task_reply(plan(), evidence)
    assert "工具统计为4" in reply and "原始事实" in reply
    assert "custom.read" not in reply and "evidence_id" not in reply and '"依据"' not in reply
    assert evidence[1].data["分析"][0]["证据"] == "source"


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        json.dumps(
            {"findings": [{"explanation": "x", "evidence_id": "old-turn", "pointer": "/count"}], "limitations": ["x"]}
        ),
        json.dumps(
            {"findings": [{"explanation": "x", "evidence_id": "source", "pointer": "/missing"}], "limitations": ["x"]}
        ),
        json.dumps({"findings": [], "limitations": []}),
    ],
)
def test_invalid_output_and_unavailable_citations_fail_closed(response):
    async def model(*_args):
        return response

    additions = asyncio.run(build_analysis_evidence(plan(), [fact()], model))
    assert not additions[0].ok
    assert additions[0].error_code == "analysis_unavailable"
    assert evaluate_plan(plan(), [fact(), *additions])[2].state == "blocked"


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("no configuration"),
        RuntimeError("rate limited"),
        TimeoutError("timeout"),
        RuntimeError("provider failed"),
    ],
)
def test_provider_errors_are_failed_analysis_without_replaying_reads(failure):
    async def model(*_args):
        raise failure

    additions = asyncio.run(build_analysis_evidence(plan(), [fact()], model))
    assert len(additions) == 1 and not additions[0].ok


def test_confirmation_and_old_task_facts_cannot_feed_analysis():
    async def model(*_args):
        pytest.fail("model must not receive uncompleted or unrelated evidence")

    value = fact().model_copy(update={"confirmation_id": "pending"})
    assert asyncio.run(build_analysis_evidence(plan(), [value], model)) == []
    assert asyncio.run(build_analysis_evidence(plan(), [fact().model_copy(update={"step_id": "old"})], model)) == []


@pytest.mark.parametrize("write_state", ["not_started", "awaiting_confirmation", "execution_unknown", "completed"])
def test_analysis_continuation_never_repeats_pending_unknown_or_completed_writes(monkeypatch, write_state):
    from services import dazah_agent_service as service
    from tools import dazah_platform as platform
    from unittest.mock import Mock
    from uuid import uuid4

    task_plan = AgentTaskPlan.model_validate(
        {
            "steps": [
                {"id": "analyze", "kind": "analysis", "goal": "分析"},
                {"id": "send", "kind": "write", "goal": "发送报告", "depends_on": ["analyze"]},
            ]
        }
    )
    payload = service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid4(),
        trace_id=uuid4(),
        session_id="test",
        message="分析并发送报告",
        subject={"user_id": "user", "tenant_id": "tenant", "source": "web"},
        source={"platform": "web"},
    )
    facts = [
        TaskEvidence(
            id="analysis",
            step_id="analyze",
            action="analysis",
            ok=True,
            occurred_at="2026-10-10T00:00:00Z",
            data={"analysis": "auxiliary"},
        )
    ]
    if write_state != "not_started":
        facts.append(
            TaskEvidence(
                id="write",
                step_id="send",
                action="execute",
                occurred_at="2026-10-10T00:00:00Z",
                write=True,
                ok=write_state != "execution_unknown",
                confirmation_id="pending" if write_state == "awaiting_confirmation" else None,
                error_code="timeout" if write_state == "execution_unknown" else None,
                data={"id": "receipt"} if write_state == "completed" else None,
            )
        )
    agent = Mock(max_iterations=30)
    platform.register_dazah_task_context("resume-test", payload.context)
    platform.configure_dazah_task_plan("resume-test", task_plan)
    monkeypatch.setattr(service, "current_dazah_task_evidence", lambda _: facts)
    try:
        service._resume_analysis_dependents(
            agent, task_plan, payload, task_id="resume-test", history=[], cancellation=None
        )
        assert agent.run_conversation.call_count == (1 if write_state == "not_started" else 0)
        assert agent.max_iterations == 30
        if write_state == "not_started":
            assert "生成确认项" in agent.run_conversation.call_args.kwargs["system_message"]
    finally:
        platform.unregister_dazah_task_context("resume-test")
