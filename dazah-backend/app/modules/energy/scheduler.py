"""Scheduled daily Wiki ingestion for the energy module."""

from __future__ import annotations

from typing import Any

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
