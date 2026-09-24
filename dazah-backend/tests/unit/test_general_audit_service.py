import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.platform.audit.models import AuditLog
from app.platform.audit.service import (
    GeneralAuditLogService,
    _category_filter,
    audit_category_of,
)


def _log(
    *,
    action: str,
    resource_type: str | None,
    method: str | None = "GET",
) -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        action=action,
        resource_type=resource_type,
        method=method,
        created_at=datetime.now(UTC),
    )


def test_audit_category_of_covers_general_audit_tabs() -> None:
    for resource in (
        "identity.user_page_permissions",
        "identity.role_page_permissions",
        "identity.permission_module_rollout",
    ):
        assert (
            audit_category_of(_log(action="页面授权调整", resource_type=resource))
            == "permissions"
        )
    assert (
        audit_category_of(
            _log(
                action="replace_user_module_permissions",
                resource_type="user_module_permissions",
            )
        )
        == "permissions"
    )
    assert (
        audit_category_of(_log(action="agent_tool_execute", resource_type="agent_tool"))
        == "agent_tools"
    )
    assert (
        audit_category_of(
            _log(action="view_agent_automation", resource_type="agent_automation")
        )
        == "automations"
    )
    assert (
        audit_category_of(
            _log(
                action="feishu_card_action_callback",
                resource_type="feishu_card_action",
                method="FEISHU",
            )
        )
        == "feishu"
    )
    for resource in (
        "feishu_gateway",
        "feishu_resource",
        "feishu_resource_change",
        "quality.feishu.inspection_record",
    ):
        assert (
            audit_category_of(_log(action="external_event", resource_type=resource))
            == "feishu"
        )
    assert (
        audit_category_of(
            _log(action="update_safety_check", resource_type="safety_check")
        )
        == "business"
    )


def test_conversation_entries_are_excluded_from_general_audit() -> None:
    log = _log(
        action="view_agent_conversation_audit",
        resource_type="agent_session",
    )

    assert audit_category_of(log) is None


def test_category_filters_compile_for_postgresql() -> None:
    statements = {
        category: str(
            select(AuditLog.id)
            .where(_category_filter(category))  # type: ignore[arg-type]
            .compile(
                dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        for category in (
            "permissions",
            "agent_tools",
            "automations",
            "feishu",
            "business",
        )
    }

    assert "user_module_permissions" in statements["permissions"]
    assert "identity.user_page_permissions" in statements["permissions"]
    assert "identity.permission_module_rollout" in statements["permissions"]
    assert "agent_tool" in statements["agent_tools"]
    assert "agent_automation" in statements["automations"]
    assert "feishu" in statements["feishu"]
    assert "feishu_resource_change" in statements["feishu"]
    assert "quality.feishu.%" in statements["feishu"]
    assert "not" in statements["business"]


def test_list_item_contains_category_specific_summary() -> None:
    log = _log(action="agent_tool_execute", resource_type="agent_tool", method="AGENT")
    log.extra = {
        "operation": "quality.list_deviations",
        "risk_level": "medium",
        "status": "succeeded",
        "request": {"password": "must-not-be-listed"},
    }

    item = GeneralAuditLogService._item(
        log,
        actor_name="审计用户",
        actor_username="audit-user",
    )

    assert item.category == "agent_tools"
    assert item.summary == {
        "operation": "quality.list_deviations",
        "risk_level": "medium",
        "status": "succeeded",
    }


def test_feishu_resource_item_exposes_external_result_identifiers() -> None:
    log = _log(
        action="base.record.update", resource_type="feishu_resource", method="HERMES"
    )
    log.extra = {
        "result": "succeeded",
        "feishu_log_id": "log-123",
        "capability": "base.record.update",
    }
    item = GeneralAuditLogService._item(log, actor_name=None, actor_username=None)
    assert item.category == "feishu"
    assert item.summary == {
        "result": "succeeded",
        "feishu_log_id": "log-123",
        "capability": "base.record.update",
    }


def test_operation_list_item_exposes_target_without_request_body() -> None:
    log = _log(action="platform_api_request", resource_type="quality")
    log.extra = {
        "operation": "查看质量记录",
        "target": "item_id=123",
        "request": {"body": {"note": "private"}},
    }
    item = GeneralAuditLogService._item(
        log, actor_name="审计用户", actor_username="audit-user"
    )
    assert item.summary == {"target": "item_id=123"}
    assert item.operation == "查看质量记录"


@pytest.mark.asyncio
async def test_operation_detail_includes_correlated_business_change() -> None:
    operation = _log(action="platform_api_request", resource_type="quality")
    operation.request_id = "request-123"
    operation.extra = {"operation": "修改质量记录"}
    related = _log(action="update_quality_item", resource_type="quality_item")
    related.request_id = operation.request_id
    related.old_value = {"status": "draft", "password": "hidden"}
    related.new_value = {"status": "approved"}

    class QuerySession:
        async def execute(self, _statement: Any) -> Any:
            return SimpleNamespace(one_or_none=lambda: (operation, "审计用户", "audit"))

        async def scalars(self, _statement: Any) -> Any:
            return SimpleNamespace(all=lambda: [related])

    detail = await GeneralAuditLogService().get_log(QuerySession(), log_id=operation.id)
    assert detail is not None
    assert detail.request_id == "request-123"
    assert detail.extra is not None
    events = detail.extra["related_events"]
    assert len(events) == 1
    assert events[0]["action"] == "update_quality_item"
    assert events[0]["old_value"] == {"status": "draft", "password": "***"}
    assert events[0]["new_value"] == {"status": "approved"}
