"""Scheduled removal of expired user operation request records only."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.platform.audit.middleware import OPERATION_ACTION
from app.platform.audit.models import AuditLog
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition


async def purge_expired_user_operations() -> int:
    cutoff = datetime.now(UTC) - timedelta(
        days=get_settings().USER_OPERATION_AUDIT_RETENTION_DAYS
    )
    removed = 0
    async with async_session_factory() as db:
        while True:
            ids = list(
                (
                    await db.scalars(
                        select(AuditLog.id)
                        .where(
                            AuditLog.action == OPERATION_ACTION,
                            AuditLog.created_at < cutoff,
                        )
                        .order_by(AuditLog.created_at)
                        .limit(1000)
                    )
                ).all()
            )
            if not ids:
                break
            await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
            await db.commit()
            removed += len(ids)
    return removed


async def run_user_operation_retention() -> None:
    await purge_expired_user_operations()


user_operation_retention_task = TaskDefinition(
    name="audit.user-operation-retention",
    module="audit",
    schedule=ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:00",
        timezone="Asia/Shanghai",
    ),
    coro=run_user_operation_retention,
    timeout_seconds=300,
)
