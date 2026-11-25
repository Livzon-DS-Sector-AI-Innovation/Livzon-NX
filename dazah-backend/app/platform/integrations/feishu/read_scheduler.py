"""Daily schedulers for quality read-only Feishu mirrors."""

import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.llm.encryption import decrypt_api_key
from app.core.secrets import decrypt_secret
from app.modules.production.models import (
    ProductionFeishuReadField,
    ProductionFeishuReadPageBinding,
    ProductionFeishuReadRecord,
    ProductionFeishuReadResource,
    ProductionFeishuReadSourceRoot,
    ProductionFeishuReadSyncRun,
)
from app.modules.production.repository import ProductionRepository
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
from app.platform.scheduler import (
    ScheduleConfig,
    SchedulerRegistry,
    ScheduleStrategy,
    TaskGenerator,
)

logger = logging.getLogger(__name__)

QUALITY_MODELS = ReadMirrorModels(
    root=QualityFeishuReadSourceRoot,
    resource=QualityFeishuReadResource,
    field=QualityFeishuReadField,
    record=QualityFeishuReadRecord,
    binding=QualityFeishuReadPageBinding,
    sync_run=QualityFeishuReadSyncRun,
    fence_sync_runs=True,
)

PRODUCTION_MODELS = ReadMirrorModels(
    root=ProductionFeishuReadSourceRoot,
    resource=ProductionFeishuReadResource,
    field=ProductionFeishuReadField,
    record=ProductionFeishuReadRecord,
    binding=ProductionFeishuReadPageBinding,
    sync_run=ProductionFeishuReadSyncRun,
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


class ProductionFeishuReadDailySyncGenerator(_DailyReadMirrorGenerator):
    """Keep the production read-mirror scheduler compatible with old jobs."""

    name = "production.feishu_read_daily_sync"
    resource_model = ProductionFeishuReadResource

    async def execute_one(self, session: Any, item: Any) -> None:
        config = await ProductionRepository(session).get_active_feishu_config()
        if config is None or not config.encrypted_app_secret:
            return
        service = ModuleFeishuReadMirrorService(
            session,
            module_code="production",
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
            models=PRODUCTION_MODELS,
        )
        await service.sync_resource(UUID(str(item)))


class QualityFeishuReadDailySyncGenerator(_DailyReadMirrorGenerator):
    name = "quality.feishu_read_daily_sync"
    resource_model = QualityFeishuReadResource

    async def execute_one(self, session: AsyncSession, item: str) -> None:
        resource_id = UUID(str(item))
        started = time.monotonic()
        try:
            await self._sync_due(session, resource_id)
        except Exception as exc:
            await session.rollback()
            # The Redis/Feishu exception may contain connection or source details.
            raise RuntimeError(
                f"Quality mirror {resource_id} sync failed ({type(exc).__name__}, "
                f"{time.monotonic() - started:.2f}s)"
            ) from None

    async def _sync_due(self, session: AsyncSession, resource_id: UUID) -> None:
        config = await session.scalar(
            select(QualityFeishuAppSettings)
            .where(
                QualityFeishuAppSettings.is_enabled.is_(True),
                QualityFeishuAppSettings.is_deleted.is_(False),
            )
            .order_by(QualityFeishuAppSettings.updated_at.desc())
        )
        if config is None or not config.app_id or not config.app_secret:
            logger.warning(
                "Quality mirror %s skipped: app configuration missing", resource_id
            )
            return
        started = time.monotonic()
        service = ModuleFeishuReadMirrorService(
            session,
            module_code="quality",
            app_id=config.app_id,
            app_secret=decrypt_api_key(config.app_secret),
            models=QUALITY_MODELS,
        )
        result = await service.sync_due_resource(resource_id, datetime.now(UTC).date())
        if result is not None:
            logger.info(
                "Quality mirror %s completed (records=%s, elapsed=%.2fs)",
                resource_id,
                result["record_count"],
                time.monotonic() - started,
            )


def register_quality_read_mirror(
    registry: SchedulerRegistry, settings: Settings, *, owner: Literal["api", "worker"]
) -> None:
    if settings.QUALITY_READ_MIRROR_SCHEDULER == owner:
        registry.register_generator(QualityFeishuReadDailySyncGenerator())
        logger.info("Quality read mirror scheduler registered (owner=%s)", owner)
