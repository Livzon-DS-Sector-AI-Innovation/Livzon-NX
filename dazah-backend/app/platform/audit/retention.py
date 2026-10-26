"""Scheduled retention for audit categories.

Read-only API request records are high volume and kept only for
``USER_OPERATION_AUDIT_RETENTION_DAYS``. Security and business audit evidence is
kept for ``AUDIT_NON_OPERATION_RETENTION_DAYS`` (three years by default); set the
value to ``0`` to disable deletion for those categories.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.platform.audit.models import AuditLog
from app.platform.audit.schemas import AuditCategory
from app.platform.audit.service import audit_retention_filter
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition

logger = logging.getLogger(__name__)

RETENTION_BATCH_SIZE = 1000
NON_OPERATION_CATEGORIES: tuple[AuditCategory, ...] = (
    "permissions",
    "business",
    "agent_tools",
    "automations",
    "feishu",
)


async def purge_expired_audit_logs(category: AuditCategory, days: int) -> int:
    """Delete expired audit rows for one category in bounded batches."""
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    removed = 0
    async with async_session_factory() as db:
        while True:
            ids = list(
                (
                    await db.scalars(
                        select(AuditLog.id)
                        .where(
                            audit_retention_filter(category),
                            AuditLog.created_at < cutoff,
                        )
                        .order_by(AuditLog.created_at)
                        .limit(RETENTION_BATCH_SIZE)
                    )
                ).all()
            )
            if not ids:
                break
            await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
            await db.commit()
            removed += len(ids)
    if removed:
        logger.info(
            "Audit retention removed %s %s records older than %s",
            removed,
            category,
            cutoff.isoformat(),
        )
    return removed


async def purge_expired_user_operations() -> int:
    """Backward-compatible entry point for operation-log retention."""
    return await purge_expired_audit_logs(
        "operations", get_settings().USER_OPERATION_AUDIT_RETENTION_DAYS
    )


async def run_audit_retention() -> None:
    settings = get_settings()
    targets: list[tuple[AuditCategory, int]] = [
        ("operations", settings.USER_OPERATION_AUDIT_RETENTION_DAYS)
    ]
    if settings.AUDIT_NON_OPERATION_RETENTION_DAYS > 0:
        targets.extend(
            (category, settings.AUDIT_NON_OPERATION_RETENTION_DAYS)
            for category in NON_OPERATION_CATEGORIES
        )
    for category, days in targets:
        await purge_expired_audit_logs(category, days)


user_operation_retention_task = TaskDefinition(
    name="audit.user-operation-retention",
    module="audit",
    schedule=ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:00",
        timezone="Asia/Shanghai",
    ),
    coro=run_audit_retention,
    timeout_seconds=1800,
)
