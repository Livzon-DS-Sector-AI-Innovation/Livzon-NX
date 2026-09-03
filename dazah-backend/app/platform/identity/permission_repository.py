from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import (
    PermissionOutboxEvent,
    User,
    UserModuleGrant,
)


class PermissionGrantRepository:
    async def has_module_view(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        module_code: str,
    ) -> bool:
        result = await db.execute(
            select(UserModuleGrant.permissions).where(
                UserModuleGrant.user_id == user_id,
                UserModuleGrant.module_code == module_code,
                UserModuleGrant.status == "active",
                UserModuleGrant.is_deleted.is_(False),
            )
        )
        permissions = result.scalar_one_or_none()
        return permissions is not None and "module.view" in permissions

    async def get_user_for_update(self, db: AsyncSession, user_id: UUID) -> User | None:
        result = await db.execute(
            select(User)
            .where(User.id == user_id, User.is_deleted.is_(False))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_grants(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        include_revoked: bool = False,
    ) -> list[UserModuleGrant]:
        stmt = select(UserModuleGrant).where(
            UserModuleGrant.user_id == user_id,
            UserModuleGrant.is_deleted.is_(False),
        )
        if not include_revoked:
            stmt = stmt.where(UserModuleGrant.status == "active")
        result = await db.execute(stmt.order_by(UserModuleGrant.module_code.asc()))
        return list(result.scalars().all())

    async def replace_grants(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        grants: list[dict[str, Any]],
        grant_version: int,
        granted_by: UUID,
    ) -> list[UserModuleGrant]:
        existing = {
            grant.module_code: grant
            for grant in await self.list_grants(
                db, user_id=user_id, include_revoked=True
            )
        }
        desired_codes = {str(item["module_code"]) for item in grants}
        for module_code, grant in existing.items():
            if module_code not in desired_codes and grant.status != "revoked":
                grant.status = "revoked"
                grant.permissions = []
                grant.data_scope = {}
                grant.grant_version = grant_version
                grant.granted_by = granted_by
                grant.updated_by = granted_by

        for item in grants:
            module_code = str(item["module_code"])
            current_grant = existing.get(module_code)
            if current_grant is None:
                current_grant = UserModuleGrant(
                    user_id=user_id,
                    module_code=module_code,
                    permissions=list(item["permissions"]),
                    data_scope=dict(item.get("data_scope") or {}),
                    grant_version=grant_version,
                    granted_by=granted_by,
                    status="active",
                )
                current_grant.created_by = granted_by
                current_grant.updated_by = granted_by
                db.add(current_grant)
                existing[module_code] = current_grant
            else:
                current_grant.permissions = list(item["permissions"])
                current_grant.data_scope = dict(item.get("data_scope") or {})
                current_grant.grant_version = grant_version
                current_grant.granted_by = granted_by
                current_grant.status = "active"
                current_grant.updated_by = granted_by
        await db.flush()
        return [existing[code] for code in sorted(desired_codes)]

    async def create_outbox_event(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        grant_version: int,
        actor_id: UUID,
        event_type: str = "identity.user_module_grants.changed.v1",
    ) -> PermissionOutboxEvent:
        event = PermissionOutboxEvent(
            event_type=event_type,
            user_id=user_id,
            grant_version=grant_version,
            payload={"user_id": str(user_id), "grant_version": grant_version},
            status="pending",
            attempts=0,
        )
        event.created_by = actor_id
        event.updated_by = actor_id
        db.add(event)
        await db.flush()
        return event

    async def mark_outbox_processed(
        self,
        db: AsyncSession,
        event: PermissionOutboxEvent,
        *,
        actor_id: UUID | None = None,
    ) -> None:
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        event.last_error = None
        event.next_attempt_at = None
        event.attempts += 1
        event.updated_by = actor_id
        await db.flush()

    async def mark_outbox_failed(
        self,
        db: AsyncSession,
        event: PermissionOutboxEvent,
        *,
        error: str,
        actor_id: UUID | None = None,
    ) -> None:
        event.status = "failed"
        event.attempts += 1
        event.last_error = error[:2000]
        backoff_seconds = min(300, 2 ** min(event.attempts, 8))
        event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
        event.updated_by = actor_id
        await db.flush()
