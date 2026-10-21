"""Scheduled daily Wiki ingestion for the energy module."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.energy.wiki_service import EnergyWikiService
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class EnergyWikiSyncGenerator(TaskGenerator):
    """Polls for a due energy source and locks the config before processing it."""

    name = "energy.wiki_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=15 * 60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 15 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: Any) -> list[str]:
        service = EnergyWikiService(session)
        config = await service.repo.get_config()
        if config is None or not config.is_active:
            return []
        return [str(config.id)]

    async def execute_one(self, session: Any, item: Any) -> None:
        del item
        await EnergyWikiService(session).run_scheduled_sync_if_due()


class EnergyNativeEntryGenerator(TaskGenerator):
    """Native tasks and persistent notification outbox, in Shanghai time."""

    name = "energy.native_entry"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 600

    async def find_due(self, session: AsyncSession) -> list[str]:
        return ["native"]

    async def execute_one(self, session: AsyncSession, item: object) -> None:
        from app.modules.energy.ledger_notifications import run_native_schedule

        await run_native_schedule(session)


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
