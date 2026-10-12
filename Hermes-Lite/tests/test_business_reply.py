import uuid

import pytest

from services.agent_task_contract import AgentTaskPlan, TaskEvidence, render_task_reply, safe_business_value


def contacts(total=825):
    return {
        "data": [{"id": f"record-{i}", "name": f"测试人员{i}", "department": "测试部门"} for i in range(100)],
        "meta": {"page": 1, "page_size": 100, "total": total},
    }


def reply(data, request="查询人事飞书联系人有多少人"):
    plan = AgentTaskPlan.model_validate({"steps": [{"id": "q", "kind": "read", "goal": request}]})
    fact = TaskEvidence(id=uuid.uuid4().hex, step_id="q", action="execute", ok=True, write=False,
                        data=safe_business_value(data), occurred_at="2026-10-12T10:00:00+08:00")
    return render_task_reply(plan, [fact])


@pytest.mark.parametrize("total", [825, 0])
def test_count_answer_uses_paginated_total_without_dumping_contact_samples(total):
    text = reply(contacts(total))
    assert str(total) in text
    assert "测试人员" not in text and "record-" not in text
    assert '"meta"' not in text and '"data"' not in text and "本轮工具返回内容" not in text
    assert "查询范围" in text


@pytest.mark.parametrize("data", [{"items": [], "total": 825}, {"count": 825}])
def test_count_answer_handles_other_valid_total_shapes(data):
    assert "825" in reply(data)


@pytest.mark.parametrize("total", [None, "825", True, -1])
def test_invalid_totals_do_not_turn_a_sample_into_a_total(total):
    text = reply(contacts(total))
    assert "无法确认总数" in text
    assert "100" not in text and "825" not in text


def test_list_answer_is_readable_and_preserves_pagination_scope():
    text = reply(contacts(), request="列出联系人")
    assert "825" in text and "测试人员0" in text and "测试部门" in text
    assert "测试人员99" not in text
    assert "仅展示" in text and '"data"' not in text and '"name"' not in text


def test_generic_business_data_and_empty_results_are_readable():
    text = reply({"record_id": "REAL-001", "amount": 12}, request="查看记录")
    assert "REAL-001" in text and "12" in text and "{" not in text
    assert "未找到" in reply({"items": [], "total": 0}, request="列出记录")
