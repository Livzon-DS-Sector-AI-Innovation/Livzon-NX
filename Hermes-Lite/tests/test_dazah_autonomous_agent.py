import asyncio
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from services import dazah_agent_service as service
from services.agent_task_contract import AgentTaskPlan
from tools import dazah_platform as platform


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("capability", [False, True])
def test_agent_discovers_new_tools_and_composes_goal_specific_reply(monkeypatch, stream, capability):
    """A new backend operation works without a Hermes business whitelist."""
    requests = []
    agent_calls = []
    real_client = httpx.AsyncClient
    entries = [
        {"operation": "new_module.find_alerts", "summary": "查找异常线索", "write": False},
        {"operation": "new_module.read_alert", "summary": "读取异常详情", "write": False},
    ]

    def transport(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": entries if not body["query"] else []})
        if request.method == "GET":
            operation = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"data": {
                "operation": operation, "write": False, "confirmation_required": False,
                "input_schema": {"type": "object", "properties": {"alert_id": {"type": "string"}}},
            }})
        return httpx.Response(200, json={"data": {"ok": True, "data": {"alert_id": "REAL-001", "status": "open"}}})

    async def planner(_payload):
        return AgentTaskPlan.model_validate({"steps": [{
            "id": "goal", "kind": "capability" if capability else "read", "goal": "定位异常",
        }]})

    async def writer(messages, task):
        assert task == "agent_grounded_reply"
        inputs = json.loads(messages[-1]["content"])
        facts = [item for item in inputs["evidence"] if item["ok"] and item["action"] == ("search" if capability else "execute")]
        assert "FAKE-999" not in json.dumps(inputs)
        return json.dumps({"sections": [{
            "step_id": "goal", "state": "completed",
            "text": "我可以帮你定位异常并读取详情。" if capability else "找到 REAL-001，它仍处于待处理状态。",
            "citations": [{"evidence_id": facts[-1]["id"], "pointer": ""}],
        }]}, ensure_ascii=False)

    class Agent:
        max_iterations = 30

        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, message, **kwargs):
            agent_calls.append(message)
            task_id = kwargs["task_id"]
            assert "不套统一卡片模板" in kwargs["system_message"]
            assert platform.current_dazah_request_context(task_id)["user_id"] == "trusted-user"
            empty = json.loads(asyncio.run(platform.dazah_tool("search", query="异常线索", task_id=task_id, step_id="goal")))
            assert empty["data"] == []
            directory = json.loads(asyncio.run(platform.dazah_tool("search", query="", limit=50, task_id=task_id, step_id="goal")))
            if not capability:
                # The agent selects from the runtime directory and follows new evidence.
                for entry in directory["data"]:
                    asyncio.run(platform.dazah_tool("describe", operation=entry["operation"], task_id=task_id, step_id="goal"))
                    asyncio.run(platform.dazah_tool("execute", operation=entry["operation"],
                        params={} if entry == entries[0] else {"alert_id": "REAL-001"}, task_id=task_id, step_id="goal"))
            return {"final_response": "FAKE-999"}

    async def proxy_ok():
        return None

    async def no_skills(_payload):
        return []

    async def no_memory(_payload, message, _trace):
        return message

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs))
    monkeypatch.setattr(service, "_require_token", lambda _token: None)
    monkeypatch.setattr(service, "_check_dazah_llm_proxy", proxy_ok)
    monkeypatch.setattr(service, "_resolve_progressive_skills", no_skills)
    monkeypatch.setattr(service, "_finalize_user_memory", no_memory)
    monkeypatch.setattr(service, "_plan_business_task", planner)
    monkeypatch.setattr(service, "_call_memory_llm", writer)
    monkeypatch.setattr(service, "DazahAIAgent", Agent)
    payload = {
        "protocol_version": "2.0", "run_id": str(uuid.uuid4()), "trace_id": str(uuid.uuid4()),
        "session_id": "autonomous-test", "message": "你可以帮我做什么呢" if capability else "帮我定位异常并看看详情",
        "subject": {"tenant_id": "test-tenant", "user_id": "trusted-user", "source": "web"},
        "source": {"platform": "web"},
    }
    previous_tasks = set(platform._task_request_contexts)
    response = TestClient(service.app).post("/v2/agent/runs" + ("/stream" if stream else ""), json=payload)
    assert response.status_code == 200
    assert set(platform._task_request_contexts) == previous_tasks
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert all(event["trace_id"] == payload["trace_id"] for event in events)
        result = next(event["data"] for event in events if event["type"] == "finished")
    else:
        result = response.json()
    assert len(agent_calls) == 1
    assert "FAKE-999" not in response.text
    assert "数据查询 goal" not in result["message"] and "本轮目录匹配结果" not in result["message"]
    searches = [body for _method, path, body in requests if path.endswith("/search")]
    assert [body["query"] for body in searches] == ["异常线索", ""]
    assert searches[-1]["limit"] == 50
    executions = [body for _method, path, body in requests if path.endswith("/execute")]
    if capability:
        assert not executions
        assert result["message"] == "我可以帮你定位异常并读取详情。"
    else:
        assert [body["operation"] for body in executions] == [item["operation"] for item in entries]
        assert executions[-1]["params"] == {"alert_id": "REAL-001"}
        assert "REAL-001" in result["message"]


def test_missing_inputs_do_not_block_schema_discovery_but_still_block_execution(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"operation": "new_module.read_alert", "write": False}})

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    platform.register_dazah_task_context("discovery", {"tenant_id": "t", "user_id": "u"})
    platform.configure_dazah_task_plan("discovery", AgentTaskPlan.model_validate({"steps": [
        {"id": "first", "kind": "read", "goal": "查找记录"},
        {"id": "next", "kind": "read", "goal": "读取详情", "depends_on": ["first"], "missing_inputs": ["对象"]},
    ]}))
    try:
        asyncio.run(platform.dazah_tool("describe", operation="new_module.read_alert", task_id="discovery", step_id="next"))
        result = json.loads(asyncio.run(platform.dazah_tool("execute", operation="new_module.read_alert", task_id="discovery", step_id="next")))
        assert len(requests) == 1 and requests[0].method == "GET"
        assert result["error"] == "step_dependencies_or_inputs_missing"
    finally:
        platform.unregister_dazah_task_context("discovery")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("composition", ["valid", "repair", "unavailable"])
def test_count_question_answers_total_after_real_tool_chain(monkeypatch, stream, composition):
    operation = "new_module.list_contacts"
    executions = []
    model_calls = []
    real_client = httpx.AsyncClient

    def respond(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": [{"operation": operation, "summary": "查询联系人", "write": False}]})
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"operation": operation, "write": False, "result_kind": "records"}})
        executions.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"ok": True, "data": {
            "data": [{"id": f"person-{i}", "name": f"测试人员{i}"} for i in range(100)],
            "meta": {"page": 1, "page_size": 100, "total": 825},
        }}})

    async def planner(_payload):
        return AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": "查询联系人"}]})

    async def writer(messages, task):
        model_calls.append(task)
        if composition == "unavailable":
            raise RuntimeError("synthetic provider failure")
        facts = json.loads(messages[-1]["content"])["evidence"]
        assert len(facts) == 1 and facts[0]["data"]["meta"]["total"] == 825
        pointer = "/data/meta/total" if composition == "repair" and len(model_calls) == 1 else "/meta/total"
        return json.dumps({"sections": [{"step_id": "q", "state": "completed",
            "text": "当前你有权限查询的人事飞书联系人共825人。",
            "citations": [{"evidence_id": facts[0]["id"], "pointer": pointer}],
        }]}, ensure_ascii=False)

    class Agent:
        max_iterations = 30

        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, _message, **kwargs):
            for action in ("search", "describe", "execute"):
                asyncio.run(platform.dazah_tool(action, operation=operation if action != "search" else None,
                    query="联系人", params={"page_size": 100}, task_id=kwargs["task_id"], step_id="q"))
            return {"final_response": '{"data": "unprocessed tool response"}'}

    async def proxy_ok():
        return None

    async def no_skills(_payload):
        return []

    async def no_memory(_payload, message, _trace):
        return message

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(platform.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(service, "_require_token", lambda _token: None)
    monkeypatch.setattr(service, "_check_dazah_llm_proxy", proxy_ok)
    monkeypatch.setattr(service, "_resolve_progressive_skills", no_skills)
    monkeypatch.setattr(service, "_finalize_user_memory", no_memory)
    monkeypatch.setattr(service, "_plan_business_task", planner)
    monkeypatch.setattr(service, "_call_memory_llm", writer)
    monkeypatch.setattr(service, "DazahAIAgent", Agent)
    payload = {
        "protocol_version": "2.0", "run_id": str(uuid.uuid4()), "trace_id": str(uuid.uuid4()),
        "session_id": "count-test", "message": "查询人事飞书联系人有多少人",
        "subject": {"tenant_id": "test-tenant", "user_id": "trusted-user", "source": "web"},
        "source": {"platform": "web"},
    }
    response = TestClient(service.app).post("/v2/agent/runs" + ("/stream" if stream else ""), json=payload)
    assert response.status_code == 200
    if stream:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [item["sequence"] for item in events] == list(range(1, len(events) + 1))
        answer = next(item["data"]["message"] for item in events if item["type"] == "finished")
    else:
        answer = response.json()["message"]
    assert "825" in answer
    assert "测试人员" not in answer and "person-" not in answer and '"data"' not in answer and '"meta"' not in answer
    assert "本轮工具返回内容" not in answer
    assert len(executions) == 1
    assert len(model_calls) == (2 if composition == "repair" else 1)
