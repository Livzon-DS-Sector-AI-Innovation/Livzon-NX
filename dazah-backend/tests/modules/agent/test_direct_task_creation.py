from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

from app.modules.agent.agent_tools import (
    DirectAutomationActionInput,
    DirectAutomationCreateInput,
    DirectScheduledTaskCreateInput,
    _direct_automation_request,
)
from app.modules.agent.automation_runner import _resolve_references
from app.modules.agent.service import AgentService
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry

SimpleNamespace: Any = _SimpleNamespace


def _action() -> DirectAutomationActionInput:
    return DirectAutomationActionInput(
        operation="identity.deliver_feishu_message",
        body={
            "recipient_user_ids": ["00000000-0000-0000-0000-000000000001"],
            "title": "通知",
            "markdown": "请查收",
            "idempotency_key": "test-delivery",
        },
    )


def test_direct_automation_is_manual_and_has_no_schedule() -> None:
    request = _direct_automation_request(
        DirectAutomationCreateInput(name="发送通知", actions=[_action()]),
        scheduled=False,
    )

    assert request.triggers[0].trigger_type.value == "manual"
    assert request.triggers[0].schedule == {}
    assert request.definition.steps[0].operation == "identity.deliver_feishu_message"  # type: ignore[union-attr]


def test_direct_scheduled_task_forces_schedule_trigger() -> None:
    request = _direct_automation_request(
        DirectScheduledTaskCreateInput(
            name="每日通知",
            requirement="每个工作日上午九点发送提醒",
            actions=[_action()],
            cron="0 9 * * 1-5",
        ),
        scheduled=True,
    )

    assert request.triggers[0].trigger_type.value == "schedule"
    assert request.triggers[0].schedule == {"cron": "0 9 * * 1-5"}
    assert request.triggers[0].timezone == "Asia/Shanghai"


def test_direct_scheduled_task_accepts_once_and_interval_schedules() -> None:
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    once = _direct_automation_request(
        DirectScheduledTaskCreateInput(
            name="单次通知",
            requirement="明天下午三点提醒我",
            actions=[_action()],
            schedule={"kind": "once", "run_at": tomorrow},
        ),
        scheduled=True,
    )
    interval = _direct_automation_request(
        DirectScheduledTaskCreateInput(
            name="定期通知",
            requirement="每两小时提醒我",
            actions=[_action()],
            schedule={"kind": "interval", "every": 2, "unit": "hours"},
        ),
        scheduled=True,
    )

    assert once.triggers[0].schedule["kind"] == "once"
    assert interval.triggers[0].schedule == {
        "kind": "interval",
        "every": 2,
        "unit": "hours",
    }


def test_scheduled_data_delivery_keeps_requirement_and_runtime_query_result() -> None:
    request = _direct_automation_request(
        DirectScheduledTaskCreateInput(
            name="上月采购汇总",
            requirement="每月一日查询上月全部采购订单并将完整汇总发送给张三",
            actions=[
                DirectAutomationActionInput(
                    operation="procurement.list_purchase_orders",
                    body={"page": 1, "page_size": 100},
                ),
                DirectAutomationActionInput(
                    operation="identity.deliver_feishu_message",
                    body={
                        "recipient_user_ids": ["00000000-0000-0000-0000-000000000001"],
                        "title": "上月采购汇总",
                        "markdown": "您好，以下是上月采购汇总。",
                        "idempotency_key": "monthly-procurement",
                    },
                ),
            ],
            cron="0 9 1 * *",
        ),
        scheduled=True,
    )

    assert request.definition.description == (
        "每月一日查询上月全部采购订单并将完整汇总发送给张三"
    )
    delivery_input = request.definition.steps[1].input  # type: ignore[union-attr]
    assert "${steps.action_1}" in delivery_input["markdown"]


def test_scheduled_data_delivery_rejects_missing_runtime_query() -> None:
    try:
        DirectScheduledTaskCreateInput(
            name="上月采购汇总",
            requirement="每月查询上月采购数据汇总并发送给张三",
            actions=[_action()],
            cron="0 9 1 * *",
        )
    except ValueError as exc:
        assert "必须先添加查询动作" in str(exc)
    else:
        raise AssertionError("missing runtime query should be rejected")


def test_reference_interpolation_serializes_complete_query_result() -> None:
    resolved = _resolve_references(
        "您好，以下是查询结果：\n${steps.action_1}",
        {
            "action_1": {
                "items": [{"order_no": "PO-001", "amount": 1250}],
                "total": 1,
            }
        },
    )

    assert "PO-001" in resolved
    assert '"total": 1' in resolved


def test_legacy_workflow_tools_are_not_registered() -> None:
    ensure_agent_tools_registered()

    assert tool_registry.get("agent.create_automation") is not None
    assert tool_registry.get("agent.create_scheduled_task") is not None
    assert tool_registry.get("agent.create_workflow") is None
    assert tool_registry.get("agent.run_workflow") is None


def test_draft_creation_does_not_require_confirmation_but_activation_does() -> None:
    ensure_agent_tools_registered()

    draft = tool_registry.require("agent.create_scheduled_task")
    confirm = tool_registry.require("agent.confirm_automation")

    assert draft.write is True
    assert draft.confirmation_required is False
    assert confirm.confirmation_required is True


def test_confirmation_ttl_uses_configured_setting() -> None:
    service = AgentService(
        settings=SimpleNamespace(AGENT_WRITE_CONFIRM_TTL_SECONDS=300),
    )

    assert service.tool_executor.confirmation_ttl_seconds == 300


def test_confirmation_ttl_defaults_to_five_minutes() -> None:
    service = AgentService(settings=SimpleNamespace())

    assert service.tool_executor.confirmation_ttl_seconds == 300
