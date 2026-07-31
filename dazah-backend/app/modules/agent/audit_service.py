import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.platform.identity.models import User

from .models import AgentConfirmation, AgentMessage, AgentSession, AgentToolCall
from .schemas import (
    AgentAuditConfirmationItem,
    AgentAuditMessageItem,
    AgentAuditOperationItem,
    AgentAuditSessionDetail,
    AgentAuditSessionItem,
    AgentAuditSessionPage,
)

_SENSITIVE_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
)
_REDACTED = "[REDACTED]"


def _session_channel_filter(channel: str) -> ColumnElement[bool]:
    return func.coalesce(AgentSession.context["channel"].astext, "web") == channel


def redact_audit_value(value: Any) -> Any:
    """Recursively remove credentials before returning audit data to the UI."""
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if any(
                    fragment in str(key).lower() for fragment in _SENSITIVE_FRAGMENTS
                )
                else redact_audit_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_value(item) for item in value]
    return value


class AgentAuditService:
    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        user_id: uuid.UUID | None = None,
        channel: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> AgentAuditSessionPage:
        message_count = (
            select(func.count(AgentMessage.id))
            .where(
                AgentMessage.session_id == AgentSession.id,
                AgentMessage.is_deleted.is_(False),
            )
            .correlate(AgentSession)
            .scalar_subquery()
        )
        tool_call_count = (
            select(func.count(AgentToolCall.id))
            .where(
                AgentToolCall.session_id == AgentSession.id,
                AgentToolCall.is_deleted.is_(False),
            )
            .correlate(AgentSession)
            .scalar_subquery()
        )
        failed_count = (
            select(func.count(AgentToolCall.id))
            .where(
                AgentToolCall.session_id == AgentSession.id,
                AgentToolCall.is_deleted.is_(False),
                AgentToolCall.status.in_(("failed", "rejected", "denied")),
            )
            .correlate(AgentSession)
            .scalar_subquery()
        )
        filters: list[ColumnElement[bool]] = [
            AgentSession.is_deleted.is_(False),
            AgentSession.user_id.is_not(None),
        ]
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    User.name.ilike(pattern),
                    User.username.ilike(pattern),
                    User.department.ilike(pattern),
                    AgentSession.title.ilike(pattern),
                )
            )
        if user_id:
            filters.append(AgentSession.user_id == user_id)
        if channel:
            filters.append(_session_channel_filter(channel))
        if started_at:
            filters.append(AgentSession.created_at >= started_at)
        if ended_at:
            filters.append(AgentSession.created_at <= ended_at)

        total = await db.scalar(
            select(func.count(AgentSession.id))
            .join(User, User.id == AgentSession.user_id)
            .where(*filters)
        )
        rows = await db.execute(
            select(
                AgentSession,
                User,
                message_count.label("message_count"),
                tool_call_count.label("tool_call_count"),
                failed_count.label("failed_count"),
            )
            .join(User, User.id == AgentSession.user_id)
            .where(*filters)
            .order_by(AgentSession.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            self._session_item(session, user, messages, tools, failed)
            for session, user, messages, tools, failed in rows.all()
        ]
        return AgentAuditSessionPage(
            items=items, page=page, page_size=page_size, total=total or 0
        )

    async def get_session_detail(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> AgentAuditSessionDetail | None:
        row = (
            await db.execute(
                select(AgentSession, User)
                .join(User, User.id == AgentSession.user_id)
                .where(
                    AgentSession.id == session_id,
                    AgentSession.is_deleted.is_(False),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        session, user = row
        messages = list(
            (
                await db.scalars(
                    select(AgentMessage)
                    .where(
                        AgentMessage.session_id == session_id,
                        AgentMessage.is_deleted.is_(False),
                    )
                    .order_by(AgentMessage.created_at.asc())
                )
            ).all()
        )
        operations = list(
            (
                await db.scalars(
                    select(AgentToolCall)
                    .where(
                        AgentToolCall.session_id == session_id,
                        AgentToolCall.is_deleted.is_(False),
                    )
                    .order_by(AgentToolCall.created_at.asc())
                )
            ).all()
        )
        confirmations = list(
            (
                await db.scalars(
                    select(AgentConfirmation)
                    .where(
                        AgentConfirmation.session_id == session_id,
                        AgentConfirmation.is_deleted.is_(False),
                    )
                    .order_by(AgentConfirmation.created_at.asc())
                )
            ).all()
        )
        return AgentAuditSessionDetail(
            session=self._session_item(
                session,
                user,
                len(messages),
                len(operations),
                sum(
                    item.status in {"failed", "rejected", "denied"}
                    for item in operations
                ),
            ),
            context=redact_audit_value(session.context),
            messages=[
                AgentAuditMessageItem(
                    id=item.id,
                    role=item.role,
                    content=item.content,
                    metadata=redact_audit_value(item.message_metadata),
                    created_at=item.created_at,
                )
                for item in messages
            ],
            operations=[
                AgentAuditOperationItem(
                    id=item.id,
                    operation=item.operation,
                    status=item.status,
                    request_payload=redact_audit_value(item.request_payload),
                    response_payload=redact_audit_value(item.response_payload),
                    error_message=item.error_message,
                    correlation_id=item.correlation_id,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in operations
            ],
            confirmations=[
                AgentAuditConfirmationItem(
                    id=item.id,
                    operation=item.operation,
                    summary=item.summary,
                    risk_level=item.risk_level,
                    status=item.status,
                    request_payload=redact_audit_value(item.request_payload),
                    result_payload=redact_audit_value(item.result_payload),
                    expires_at=item.expires_at,
                    executed_at=item.executed_at,
                    created_at=item.created_at,
                )
                for item in confirmations
            ],
        )

    @staticmethod
    def _session_item(
        session: AgentSession,
        user: User,
        message_count: int,
        tool_call_count: int,
        failed_count: int,
    ) -> AgentAuditSessionItem:
        return AgentAuditSessionItem(
            id=session.id,
            user_id=user.id,
            user_name=user.name,
            username=user.username,
            department=user.department,
            title=session.title,
            status=session.status,
            channel=str(session.context.get("channel") or "web"),
            message_count=message_count,
            tool_call_count=tool_call_count,
            failed_operation_count=failed_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
