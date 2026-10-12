import asyncio
import json

import pytest

from services.agent_task_contract import AgentTaskPlan, TaskEvidence
from services.grounded_reply import compose_task_reply


def plan(kind="read"):
    return AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": kind, "goal": "查找需要处理的记录"}]})


def evidence(**kwargs):
    return TaskEvidence(id="fact", step_id="q", action="execute", ok=True, write=False,
                        occurred_at="2026-10-12T08:00:00+08:00", operation="custom.read_records",
                        data={"total": 2}, filters={"status": "open"}, **kwargs)


def output(state="completed", citations=None):
    return {"sections": [{"step_id": "q", "state": state, "text": "当前有两条记录需要处理。",
                          "citations": citations if citations is not None else [
                              {"evidence_id": "fact", "pointer": "/total"}]}]}


def test_valid_natural_reply_checks_citations_without_exposing_details():
    async def llm(messages, task):
        assert task == "agent_grounded_reply"
        inputs = json.loads(messages[-1]["content"])
        assert inputs["outcomes"][0]["state"] == "completed"
        assert inputs["evidence"][0]["data"] == {"total": 2}
        assert inputs["evidence"][0]["output_hint"] == "只查询本地缓存"
        return json.dumps(output(), ensure_ascii=False)

    reply = asyncio.run(compose_task_reply("帮我看看哪些记录需要处理", plan(), [evidence(output_hint="只查询本地缓存")], llm))
    assert reply.startswith("当前有两条记录需要处理。")
    assert reply == "当前有两条记录需要处理。"
    assert "来源：" not in reply and "查询条件：" not in reply
    assert "数据查询 q" not in reply and '"total"' not in reply


@pytest.mark.parametrize("label", ["能力介绍", "任务", "来源", "查询条件", "数据依据"])
def test_model_cannot_reintroduce_hidden_detail_sections(label):
    async def llm(*_args):
        result = output()
        result["sections"][0]["text"] = f"当前有两条记录。\n{label}：internal-detail"
        return json.dumps(result, ensure_ascii=False)

    reply = asyncio.run(compose_task_reply("query", plan(), [evidence()], llm))
    assert "internal-detail" not in reply
    assert "总数：2" in reply and '"total"' not in reply
    assert "来源：" not in reply and "查询条件：" not in reply


@pytest.mark.parametrize("change", ["missing_id", "missing_pointer", "wrong_state", "omitted_step", "no_citations",
                                    "foreign_step", "failed_fact", "directory_as_records", "null", "invalid", "oversized"])
def test_invalid_grounding_falls_back_without_unverified_prose(change):
    result = output()
    facts = [evidence()]
    if change == "missing_id":
        result["sections"][0]["citations"][0]["evidence_id"] = "invented"
    elif change == "missing_pointer":
        result["sections"][0]["citations"][0]["pointer"] = "/invented"
    elif change == "wrong_state":
        result["sections"][0]["state"] = "failed"
    elif change == "omitted_step":
        result["sections"][0]["step_id"] = "other"
    elif change == "no_citations":
        result["sections"][0]["citations"] = []
    elif change == "foreign_step":
        facts[0].step_id = "other"
    elif change == "failed_fact":
        facts[0].ok = False
    elif change == "directory_as_records":
        facts[0].action = "search"
    elif change == "null":
        facts[0].data = {"total": None}

    async def llm(*_args):
        if change == "invalid":
            return "invalid JSON"
        if change == "oversized":
            return "x" * 32001
        result["sections"][0]["text"] = "FAKE-999"
        return json.dumps(result)

    reply = asyncio.run(compose_task_reply("query", plan(), facts, llm))
    assert "FAKE-999" not in reply


@pytest.mark.parametrize("error", [RuntimeError("no config"), RuntimeError("rate limit"),
                                  RuntimeError("provider failed"), TimeoutError("timeout")])
def test_model_failure_preserves_verified_facts(error):
    async def llm(*_args):
        raise error

    reply = asyncio.run(compose_task_reply("query", plan(), [evidence()], llm))
    assert "总数：2" in reply and '"total"' not in reply
    assert "来源：" not in reply and "查询条件：" not in reply and "custom.read_records" not in reply


def test_pending_confirmation_stays_pending_in_natural_response():
    fact = evidence().model_copy(update={"write": True, "data": None, "confirmation_id": "pending"})

    async def llm(*_args):
        return json.dumps(output("awaiting_confirmation", citations=[]))

    reply = asyncio.run(compose_task_reply("创建记录", plan("write"), [fact], llm))
    assert "待确认，尚未执行" in reply


def test_pending_state_metadata_cannot_authorize_a_completed_write_claim():
    fact = evidence().model_copy(update={"write": True, "data": None, "confirmation_id": "pending"})

    async def llm(*_args):
        result = output("awaiting_confirmation", citations=[])
        result["sections"][0]["text"] = "已发送完成。"
        return json.dumps(result, ensure_ascii=False)

    reply = asyncio.run(compose_task_reply("发送结果", plan("write"), [fact], llm))
    assert "已发送" not in reply and "待确认，尚未执行" in reply


def test_capability_reply_uses_directory_instead_of_operation_listing():
    fact = evidence().model_copy(update={"action": "search", "operation": None, "data": [
        {"operation": "new_module.find_alerts", "summary": "定位异常记录", "write": False}]})

    async def llm(*_args):
        result = output(citations=[{"evidence_id": "fact", "pointer": "/0/summary"}])
        result["sections"][0]["text"] = "我可以帮你定位异常记录，方便你安排后续处理。"
        return json.dumps(result, ensure_ascii=False)

    reply = asyncio.run(compose_task_reply("你能帮我做什么", plan("capability"), [fact], llm))
    assert "定位异常记录" in reply and "new_module." not in reply


def test_count_composition_uses_total_citation_instead_of_page_sample():
    fact = evidence().model_copy(update={"data": {
        "data": [{"name": "测试人员"}, {"展示范围": "仅展示前3条，本次结果共100条"}],
        "meta": {"page": 1, "page_size": 100, "total": 825},
    }})

    async def llm(messages, task):
        inputs = json.loads(messages[-1]["content"])
        assert "/meta/total" in inputs["citation_choices"][0]["pointers"]
        assert inputs["answer_focus"] == "count"
        result = output(citations=[{"evidence_id": "fact", "pointer": "/meta/total"}])
        result["sections"][0]["text"] = "当前你有权限查询的人事飞书联系人共825人。"
        return "```json\n" + json.dumps(result, ensure_ascii=False) + "\n```"

    text = asyncio.run(compose_task_reply("查询人事飞书联系人有多少人", plan(), [fact], llm))
    assert "825人" in text and "测试人员" not in text and "meta" not in text


def test_bad_citation_is_corrected_once_without_replaying_tools():
    calls = []

    async def llm(messages, task):
        calls.append((messages, task))
        result = output(citations=[{"evidence_id": "fact", "pointer": "/data/total" if len(calls) == 1 else "/total"}])
        if len(calls) == 2:
            assert "citation_pointer" in messages[0]["content"]
        return json.dumps(result, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("query", plan(), [evidence()], llm))
    assert len(calls) == 2 and text == "当前有两条记录需要处理。"


def test_raw_json_model_answer_is_rewritten_as_a_real_answer():
    calls = []

    async def llm(*_args):
        calls.append(True)
        result = output()
        result["sections"][0]["text"] = '{"total":2}' if len(calls) == 1 else "当前有两条记录。"
        return json.dumps(result, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("query", plan(), [evidence()], llm))
    assert len(calls) == 2 and text == "当前有两条记录。"


def test_count_answer_cannot_replace_authoritative_total_with_page_size():
    calls = []
    fact = evidence().model_copy(update={"data": {"meta": {"total": 825, "page_size": 100}}})

    async def llm(*_args):
        calls.append(True)
        result = output(citations=[{"evidence_id": "fact", "pointer": "/meta/total"}])
        result["sections"][0]["text"] = "当前有100人。"
        return json.dumps(result, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("联系人有多少人", plan(), [fact], llm))
    assert len(calls) == 2 and "825" in text and "100" not in text


def test_count_answer_cannot_infer_a_total_from_a_record_sample():
    fact = evidence().model_copy(update={"data": {"items": [{"name": "测试人员"}]}})

    async def llm(*_args):
        result = output(citations=[{"evidence_id": "fact", "pointer": "/items"}])
        result["sections"][0]["text"] = "当前共有1人。"
        return json.dumps(result, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("联系人有多少人", plan(), [fact], llm))
    assert "无法确认总数" in text and "共有1人" not in text


def test_model_can_explain_missing_total_without_unnecessary_repair():
    fact = evidence().model_copy(update={"data": {"items": [{"name": "测试人员"}]}})
    calls = []

    async def llm(*_args):
        calls.append(True)
        result = output(citations=[{"evidence_id": "fact", "pointer": "/items"}])
        result["sections"][0]["text"] = "当前只取得联系人样本，未提供总数，无法据此确认完整人数。"
        return json.dumps(result, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("联系人有多少人", plan(), [fact], llm))
    assert len(calls) == 1
    assert text == "当前只取得联系人样本，未提供总数，无法据此确认完整人数。"


def test_completed_analysis_offers_eligible_current_step_facts():
    from services.agent_task_contract import AgentTaskPlan, TaskEvidence

    task_plan = AgentTaskPlan.model_validate({"steps": [{"id": "assess", "kind": "analysis", "goal": "判断同步是否完整"}]})
    read = evidence().model_copy(update={"step_id": "assess"})
    analysis = TaskEvidence(id="analysis-fact", step_id="assess", action="analysis", ok=True,
        occurred_at=read.occurred_at, data={"结论": "仅凭人数无法核实同步完整性"})

    async def model(messages, _task):
        inputs = json.loads(messages[1]["content"])
        assert {item["id"] for item in inputs["evidence"]} == {"fact", "analysis-fact"}
        return json.dumps({"sections": [{"step_id": "assess", "state": "completed",
            "text": "不能仅凭人数判断同步完整，还需核对同步状态和对照数据。",
            "citations": [{"evidence_id": "analysis-fact", "pointer": "/结论"}]}]}, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("判断同步完整性", task_plan, [read, analysis], model))
    assert text.startswith("不能仅凭人数判断") and "调用失败" not in text


def test_query_and_analysis_can_merge_into_one_natural_conclusion():
    task_plan = AgentTaskPlan.model_validate({"steps": [
        {"id": "read", "kind": "read", "goal": "读取人数"},
        {"id": "assess", "kind": "analysis", "goal": "判断同步完整性", "depends_on": ["read"]},
    ]})
    read = evidence().model_copy(update={"step_id": "read"})
    analysis = TaskEvidence(id="analysis-fact", step_id="assess", action="analysis", ok=True,
        occurred_at=read.occurred_at, data={"结论": "仅凭人数无法核实同步完整性"})

    async def model(messages, _task):
        tasks = json.loads(messages[1]["content"])["reply_tasks"]
        assert tasks[0]["required"] is False and tasks[1]["required"] is True
        assert "fact" in tasks[1]["evidence_ids"]
        return json.dumps({"sections": [{"step_id": "assess", "state": "completed",
            "text": "不能，仅凭当前人数无法确认同步完整；还需对比同步状态和来源数据。",
            "citations": [{"evidence_id": "fact", "pointer": "/total"}]}]}, ensure_ascii=False)

    text = asyncio.run(compose_task_reply("判断同步完整性", task_plan, [read, analysis], model))
    assert text == "不能，仅凭当前人数无法确认同步完整；还需对比同步状态和来源数据。"
