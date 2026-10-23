import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.platform.audit import retention
from app.platform.audit.middleware import OPERATION_ACTION
from app.platform.audit.models import AuditLog


@pytest.mark.asyncio
async def test_purge_removes_only_operations_older_than_30_days(
    monkeypatch: Any, mirror_session_factory: Any
) -> None:
    monkeypatch.setattr(retention, "async_session_factory", mirror_session_factory)
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(USER_OPERATION_AUDIT_RETENTION_DAYS=30),
    )
    old = datetime.now(UTC) - timedelta(days=31)
    recent = datetime.now(UTC) - timedelta(days=1)
    expired_operation = AuditLog(
        id=uuid.uuid4(), action=OPERATION_ACTION, created_at=old
    )
    recent_operation = AuditLog(
        id=uuid.uuid4(), action=OPERATION_ACTION, created_at=recent
    )
    old_business = AuditLog(id=uuid.uuid4(), action="business_update", created_at=old)
    ids = [expired_operation.id, recent_operation.id, old_business.id]

    async with mirror_session_factory() as db:
        db.add_all([expired_operation, recent_operation, old_business])
        await db.commit()
    try:
        removed = await retention.purge_expired_user_operations()
        assert removed >= 1
        async with mirror_session_factory() as db:
            remaining = set(
                (
                    await db.scalars(select(AuditLog.id).where(AuditLog.id.in_(ids)))
                ).all()
            )
        assert remaining == {recent_operation.id, old_business.id}
    finally:
        async with mirror_session_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_non_operation_retention_keeps_conversation_audit(
    monkeypatch: Any, mirror_session_factory: Any
) -> None:
    monkeypatch.setattr(retention, "async_session_factory", mirror_session_factory)
    old = datetime.now(UTC) - timedelta(days=1096)
    old_permission = AuditLog(
        id=uuid.uuid4(),
        action="rbac_user_roles_updated",
        resource_type="identity.user_page_permissions",
        created_at=old,
    )
    old_business = AuditLog(
        id=uuid.uuid4(),
        action="business_update",
        resource_type="quality",
        created_at=old,
    )
    old_conversation = AuditLog(
        id=uuid.uuid4(), action="list_agent_conversation_audit", created_at=old
    )
    ids = [old_permission.id, old_business.id, old_conversation.id]
    async with mirror_session_factory() as db:
        db.add_all([old_permission, old_business, old_conversation])
        await db.commit()
    try:
        assert await retention.purge_expired_audit_logs("permissions", 1095) == 1
        assert await retention.purge_expired_audit_logs("business", 1095) == 1
        async with mirror_session_factory() as db:
            remaining = set(
                (
                    await db.scalars(select(AuditLog.id).where(AuditLog.id.in_(ids)))
                ).all()
            )
        assert remaining == {old_conversation.id}
    finally:
        async with mirror_session_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
            await db.commit()
