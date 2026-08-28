import uuid
from datetime import UTC, datetime

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
    assert "agent_tool" in statements["agent_tools"]
    assert "agent_automation" in statements["automations"]
    assert "feishu" in statements["feishu"]
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
