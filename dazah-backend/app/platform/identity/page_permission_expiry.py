"""Scheduled governance for expiring sensitive page permissions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.platform.audit.models import AuditLog
from app.platform.identity.models import Role, RolePageGrant, User, UserPageGrant
from app.platform.identity.page_policy import get_page_definition
from app.platform.integrations.feishu.notification import send_user_card
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition

logger = logging.getLogger(__name__)


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
    settings = get_settings()
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
        actor_ids = {
            actor_id
            for grant in [*role_grants, *user_grants]
            if (actor_id := grant.updated_by or grant.created_by) is not None
        }
        recipient_candidates = list(
            (
                await db.execute(
                    select(User).where(
                        User.is_deleted.is_(False),
                        User.status == "active",
                        (User.role == "admin") | (User.id.in_(actor_ids)),
                    )
                )
            ).scalars()
        )
        recipient_by_id = {item.id: item for item in recipient_candidates}
        admin_ids = {item.id for item in recipient_candidates if item.role == "admin"}
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
            page = get_page_definition(grant.page_key)
            page_name = page.page_name if page else grant.page_key
            delivered = 0
            if settings.FEISHU_APP_ID and settings.FEISHU_APP_SECRET:
                grant_recipient_ids = set(admin_ids)
                actor_id = grant.updated_by or grant.created_by
                if actor_id is not None:
                    grant_recipient_ids.add(actor_id)
                for recipient_id in grant_recipient_ids:
                    recipient = recipient_by_id.get(recipient_id)
                    if recipient is None:
                        continue
                    if not recipient.feishu_open_id:
                        continue
                    ok = await send_user_card(
                        recipient.feishu_open_id,
                        "高风险页面权限已到期" if expired else "高风险页面权限即将到期",
                        (
                            f"**授权对象：** {target_name}\n"
                            f"**页面：** {page_name}\n"
                            "**到期时间：** "
                            f"{expiry.astimezone().strftime('%Y-%m-%d %H:%M')}\n"
                            "请前往系统权限管理核对并续期或撤销。"
                        ),
                        app_id=settings.FEISHU_APP_ID,
                        app_secret=settings.FEISHU_APP_SECRET,
                    )
                    delivered += int(ok)
            if expired or delivered:
                await _record_event(
                    db,
                    action=event_action,
                    resource_type=resource_type,
                    grant=grant,
                    target_name=target_name,
                    expiry=expiry,
                    recipient_count=delivered,
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
