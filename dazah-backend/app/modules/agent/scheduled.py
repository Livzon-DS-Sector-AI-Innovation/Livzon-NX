from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import or_, select

from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_runner import AgentAutomationRunner
from app.modules.agent.push_delivery_service import PushDeliveryService
from app.platform.identity.models import PermissionOutboxEvent
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.scheduler.registry import (
    ScheduleConfig,
    ScheduleStrategy,
    TaskGenerator,
)


class AgentAccessScopeSyncGenerator(TaskGenerator):
    name = "agent_access_scope_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=5,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = batch_size
        self.permission_repo = PermissionGrantRepository()
        self.scope_service = AgentAccessScopeService(self.permission_repo)

    async def find_due(self, session: Any) -> list[PermissionOutboxEvent]:
        now = datetime.now(UTC)
        result = await session.execute(
            select(PermissionOutboxEvent)
            .where(
                PermissionOutboxEvent.is_deleted.is_(False),
                PermissionOutboxEvent.event_type
                == "identity.user_module_grants.changed.v1",
                PermissionOutboxEvent.status.in_(["pending", "failed"]),
                or_(
                    PermissionOutboxEvent.next_attempt_at.is_(None),
                    PermissionOutboxEvent.next_attempt_at <= now,
                ),
            )
            .order_by(PermissionOutboxEvent.created_at.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def execute_one(self, session: Any, item: PermissionOutboxEvent) -> None:
        try:
            await self.scope_service.synchronize(
                session,
                user_id=cast(uuid.UUID, item.user_id),
                actor_id=item.updated_by or item.created_by,
            )
            await self.permission_repo.mark_outbox_processed(
                session,
                item,
                actor_id=item.updated_by or item.created_by,
            )
        except Exception as exc:
            await self.permission_repo.mark_outbox_failed(
                session,
                item,
                error=str(exc),
                actor_id=item.updated_by or item.created_by,
            )


class AgentAutomationGenerator(TaskGenerator):
    """Schedules and executes persisted Livzon automation trigger windows."""

    name = "agent_automation_scheduler"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=5,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 300

    def __init__(self, batch_size: int = 50) -> None:
        self.runner = AgentAutomationRunner(batch_size=batch_size)

    async def find_due(self, session: Any) -> list[Any]:
        return await self.runner.claim_due_work(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await self.runner.execute_work(session, item)


class AgentPushDeliveryGenerator(TaskGenerator):
    """Retries durable delivery attempts and reconciles authenticated card actions."""

    name = "agent_push_delivery_scheduler"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=5,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 60

    def __init__(self, batch_size: int = 50) -> None:
        self.batch_size = batch_size
        self.service = PushDeliveryService()

    async def find_due(self, session: Any) -> list[Any]:
        await self.service.reconcile_gateway_receipts(session, limit=self.batch_size)
        return await self.service.claim_due_retries(session, limit=self.batch_size)

    async def execute_one(self, session: Any, item: Any) -> None:
        await self.service.retry_delivery(session, delivery_id=item)
