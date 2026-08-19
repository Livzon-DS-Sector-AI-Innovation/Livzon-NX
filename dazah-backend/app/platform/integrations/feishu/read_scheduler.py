"""Daily schedulers for quality read-only Feishu mirrors."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.llm.encryption import decrypt_api_key
from app.modules.quality.models import (
    QualityFeishuAppSettings,
    QualityFeishuReadField,
    QualityFeishuReadPageBinding,
    QualityFeishuReadRecord,
    QualityFeishuReadResource,
    QualityFeishuReadSourceRoot,
    QualityFeishuReadSyncRun,
)
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
    ReadMirrorModels,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

QUALITY_MODELS = ReadMirrorModels(
    root=QualityFeishuReadSourceRoot,
    resource=QualityFeishuReadResource,
    field=QualityFeishuReadField,
    record=QualityFeishuReadRecord,
    binding=QualityFeishuReadPageBinding,
    sync_run=QualityFeishuReadSyncRun,
)


class _DailyReadMirrorGenerator(TaskGenerator):
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=15 * 60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30 * 60
    enabled = True
    settings_toggle_key = ""
    resource_model: type[Any]

    async def find_due(self, session: Any) -> list[str]:
        if datetime.now(ZoneInfo(self.schedule.timezone)).hour < 2:
            return []
        result = await session.execute(
            select(self.resource_model).where(self.resource_model.is_deleted.is_(False))
        )
        today = datetime.now(UTC).date()
        return [
            str(item.id)
            for item in result.scalars().all()
            if item.last_complete_sync_at is None
            or item.last_complete_sync_at.date() < today
        ]


class QualityFeishuReadDailySyncGenerator(_DailyReadMirrorGenerator):
    name = "quality.feishu_read_daily_sync"
    resource_model = QualityFeishuReadResource

    async def execute_one(self, session: Any, item: Any) -> None:
        config = await session.scalar(
            select(QualityFeishuAppSettings)
            .where(
                QualityFeishuAppSettings.is_enabled.is_(True),
                QualityFeishuAppSettings.is_deleted.is_(False),
            )
            .order_by(QualityFeishuAppSettings.updated_at.desc())
        )
        if config is None or not config.app_secret:
            return
        service = ModuleFeishuReadMirrorService(
            session,
            module_code="quality",
            app_id=config.app_id,
            app_secret=decrypt_api_key(config.app_secret),
            models=QUALITY_MODELS,
        )
        await service.sync_resource(UUID(str(item)))
