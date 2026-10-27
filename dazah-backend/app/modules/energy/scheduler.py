"""Scheduled delivery for the native energy ledger."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class EnergyNotificationDeliveryGenerator(TaskGenerator):
    """Deliver outside the native ledger's transaction-wide calculation lock."""

    name = "energy.notification_delivery"
    schedule = ScheduleConfig(strategy=ScheduleStrategy.INTERVAL, interval_seconds=30)
    timeout_seconds = 600

    async def find_due(self, session: AsyncSession) -> list[str]:
        return ["outbox"]

    async def execute_one(self, session: AsyncSession, item: object) -> None:
        from datetime import UTC, datetime

        from app.modules.energy.ledger_notifications import deliver_notifications

        await deliver_notifications(session, datetime.now(UTC))
