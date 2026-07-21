import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.redaction import redact_sensitive
from app.platform.audit.models import AuditLog
from app.platform.audit.schemas import (
    AuditCategory,
    GeneralAuditLogDetail,
    GeneralAuditLogItem,
    GeneralAuditLogPage,
)
from app.platform.identity.models import User

_CONVERSATION_ACTIONS = frozenset(
    {
        "list_agent_conversation_audit",
        "view_agent_conversation_audit",
        "feishu_agent_message",
    }
)
_PERMISSION_RESOURCE_TYPES = frozenset(
    {"user_module_permissions", "agent_access_scope"}
)
_CATEGORY_SUMMARY_KEYS: dict[AuditCategory, tuple[str, ...]] = {
    "permissions": (
        "grant_version",
        "reason",
        "returned",
        "source_grant_version",
    ),
    "agent_tools": (
        "operation",
        "risk_level",
        "write",
        "status",
        "confirmation_id",
        "error_message",
    ),
    "automations": ("status", "returned", "source_grant_version"),
    "feishu": (
        "action_key",
        "status",
        "outcome",
        "message_id",
        "card_id",
    ),
    "business": (),
}


def audit_category_of(log: AuditLog) -> AuditCategory | None:
    if log.action in _CONVERSATION_ACTIONS:
        return None
    if log.resource_type in _PERMISSION_RESOURCE_TYPES:
        return "permissions"
    if log.resource_type == "agent_tool":
        return "agent_tools"
    if log.resource_type == "agent_automation":
        return "automations"
    if log.method == "FEISHU" or log.resource_type == "feishu_card_action":
        return "feishu"
    return "business"


def _category_filter(category: AuditCategory) -> ColumnElement[bool]:
    permissions = func.coalesce(
        AuditLog.resource_type.in_(_PERMISSION_RESOURCE_TYPES), false()
    )
    agent_tools = func.coalesce(AuditLog.resource_type == "agent_tool", false())
    automations = func.coalesce(
        AuditLog.resource_type == "agent_automation", false()
    )
    feishu = func.coalesce(
        or_(
            AuditLog.method == "FEISHU",
            AuditLog.resource_type == "feishu_card_action",
        ),
        false(),
    )
    if category == "permissions":
        return permissions
    if category == "agent_tools":
        return agent_tools
    if category == "automations":
        return automations
    if category == "feishu":
        return feishu
    return ~(permissions | agent_tools | automations | feishu)


class GeneralAuditLogService:
    async def list_logs(
        self,
        db: AsyncSession,
        *,
        category: AuditCategory,
        page: int,
        page_size: int,
        keyword: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> GeneralAuditLogPage:
        filters = [
            AuditLog.action.not_in(_CONVERSATION_ACTIONS),
            _category_filter(category),
        ]
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    AuditLog.action.ilike(pattern),
                    AuditLog.resource_type.ilike(pattern),
                    AuditLog.path.ilike(pattern),
                    User.name.ilike(pattern),
                    User.username.ilike(pattern),
                )
            )
        if started_at:
            filters.append(AuditLog.created_at >= started_at)
        if ended_at:
            filters.append(AuditLog.created_at <= ended_at)

        total = await db.scalar(
            select(func.count(AuditLog.id))
            .select_from(AuditLog)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(*filters)
        )
        rows = await db.execute(
            select(AuditLog, User.name, User.username)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            self._item(log, actor_name=name, actor_username=username)
            for log, name, username in rows.all()
        ]
        return GeneralAuditLogPage(
            items=items,
            page=page,
            page_size=page_size,
            total=total or 0,
        )

    async def get_log(
        self,
        db: AsyncSession,
        *,
        log_id: uuid.UUID,
    ) -> GeneralAuditLogDetail | None:
        row = (
            await db.execute(
                select(AuditLog, User.name, User.username)
                .outerjoin(User, User.id == AuditLog.user_id)
                .where(
                    AuditLog.id == log_id,
                    AuditLog.action.not_in(_CONVERSATION_ACTIONS),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        log, actor_name, actor_username = row
        item = self._item(
            log,
            actor_name=actor_name,
            actor_username=actor_username,
        )
        return GeneralAuditLogDetail(
            **item.model_dump(),
            request_id=log.request_id,
            duration_ms=log.duration_ms,
            old_value=redact_sensitive(log.old_value),
            new_value=redact_sensitive(log.new_value),
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            extra=redact_sensitive(log.extra),
        )

    @staticmethod
    def _item(
        log: AuditLog,
        *,
        actor_name: str | None,
        actor_username: str | None,
    ) -> GeneralAuditLogItem:
        category = audit_category_of(log)
        if category is None:
            raise ValueError("Conversation audit entries are not general audit logs")
        extra = redact_sensitive(log.extra or {}, max_string_length=500)
        summary = {
            key: extra[key]
            for key in _CATEGORY_SUMMARY_KEYS[category]
            if key in extra
        }
        return GeneralAuditLogItem(
            id=log.id,
            category=category,
            actor_user_id=log.user_id,
            actor_name=actor_name,
            actor_username=actor_username,
            action=log.action,
            method=log.method,
            path=log.path,
            status_code=log.status_code,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            summary=summary,
            created_at=log.created_at,
        )


async def record_audit_log(
    db: AsyncSession,
    *,
    action: str,
    request_id: str | None = None,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        request_id=request_id,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        extra=extra,
    )
    db.add(audit_log)
    await db.flush()
    return audit_log
