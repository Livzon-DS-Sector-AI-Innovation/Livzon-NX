"""Scheduled governance for expiring sensitive page permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.platform.audit.models import AuditLog
from app.platform.identity.models import Role, RolePageGrant, User, UserPageGrant
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition


async def _already_recorded(
    db: AsyncSession,
    *,
    action: str,
    resource_id: Any,
    expiry: datetime,
) -> bool:
    result = await db.execute(
        select(AuditLog.new_value).where(
            AuditLog.action == action,
            AuditLog.resource_id == resource_id,
        )
    )
    expiry_value = expiry.isoformat()
    return any(
        (value or {}).get("expires_at") == expiry_value for value in result.scalars()
    )


async def _record_event(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    grant: RolePageGrant | UserPageGrant,
    target_name: str,
    expiry: datetime,
    recipient_count: int = 0,
) -> None:
    db.add(
        AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=grant.id,
            new_value={
                "target_name": target_name,
                "page_key": grant.page_key,
                "sensitive_actions": list(grant.sensitive_actions or []),
                "expires_at": expiry.isoformat(),
                "recipient_count": recipient_count,
            },
        )
    )


async def scan_sensitive_page_permission_expiry() -> None:
    now = datetime.now(UTC)
    warning_at = now + timedelta(days=30)
    async with async_session_factory() as db:
        role_grants = list(
            (
                await db.execute(
                    select(RolePageGrant).where(
                        RolePageGrant.sensitive_actions_expires_at.is_not(None),
                        RolePageGrant.sensitive_actions_expires_at <= warning_at,
                        RolePageGrant.is_deleted.is_(False),
                    )
                )
            ).scalars()
        )
        user_grants = list(
            (
                await db.execute(
                    select(UserPageGrant).where(
                        UserPageGrant.sensitive_actions_expires_at.is_not(None),
                        UserPageGrant.sensitive_actions_expires_at <= warning_at,
                        UserPageGrant.is_deleted.is_(False),
                    )
                )
            ).scalars()
        )
        if not role_grants and not user_grants:
            return
        role_ids = {item.role_id for item in role_grants}
        user_ids = {item.user_id for item in user_grants}
        roles = {
            item.id: item
            for item in (
                await db.execute(select(Role).where(Role.id.in_(role_ids)))
            ).scalars()
        }
        users = {
            item.id: item
            for item in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars()
        }
        governed: list[
            tuple[str, RolePageGrant | UserPageGrant, str]
        ] = []
        for role_grant in role_grants:
            role = roles.get(role_grant.role_id)
            if role is not None:
                governed.append(("identity.role_page_grant", role_grant, role.name))
        for user_grant in user_grants:
            user = users.get(user_grant.user_id)
            if user is not None:
                governed.append(("identity.user_page_grant", user_grant, user.name))
        for resource_type, grant, target_name in governed:
            expiry = grant.sensitive_actions_expires_at
            if expiry is None:
                continue
            expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)
            expired = expiry <= now
            event_action = (
                "page_permission_sensitive_expired"
                if expired
                else "page_permission_expiry_notice"
            )
            if await _already_recorded(
                db, action=event_action, resource_id=grant.id, expiry=expiry
            ):
                continue
            await _record_event(
                db,
                action=event_action,
                resource_type=resource_type,
                grant=grant,
                target_name=target_name,
                expiry=expiry,
            )
        await db.commit()


sensitive_page_permission_expiry_task = TaskDefinition(
    name="identity.sensitive-page-permission-expiry",
    module="identity",
    schedule=ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="09:00",
        timezone="Asia/Shanghai",
    ),
    coro=scan_sensitive_page_permission_expiry,
    timeout_seconds=300,
)
