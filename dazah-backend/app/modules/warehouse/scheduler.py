"""Daily read-only Feishu mirror synchronization for warehouse."""

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo
from uuid import UUID

from app.modules.warehouse.service import WarehouseService
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class WarehouseFeishuDailySyncGenerator(TaskGenerator):
    name = "warehouse.feishu_daily_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=15 * 60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: Any) -> list[str]:
        service = WarehouseService(session)
        config = await service.repo.get_active_feishu_config()
        if config is None:
            return []
        try:
            hour, minute = (int(part) for part in config.daily_sync_time.split(":"))
            timezone = ZoneInfo(config.timezone)
        except (ValueError, KeyError):
            return []
        now = datetime.now(timezone)
        if now.time() < time(hour, minute):
            return []
        due: list[str] = []
        for table in await service.repo.list_enabled_feishu_tables():
            last_local = table.last_synced_at.astimezone(timezone) if table.last_synced_at else None
            if last_local is None or last_local.date() < now.date():
                due.append(str(table.id))
        return due

    async def execute_one(self, session: Any, item: Any) -> None:
        await WarehouseService(session).sync_feishu_table(
            UUID(str(item)), trigger_type="scheduled"
        )


class WarehouseFeishuAnalysisGenerator(TaskGenerator):
    name = "warehouse.feishu_analysis"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=5,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 10 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: Any) -> list[str]:
        runs = await WarehouseService(session).repo.claim_queued_analysis_runs(limit=4)
        return [str(run.id) for run in runs]

    async def execute_one(self, session: Any, item: Any) -> None:
        await WarehouseService(session).execute_analysis_run(UUID(str(item)))
