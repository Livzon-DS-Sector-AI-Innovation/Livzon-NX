"""Warehouse scheduled sync task — periodic feishu → local incremental sync."""

from __future__ import annotations

import logging

from app.core.database import async_session_factory
from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.modules.warehouse.service import WarehouseService
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition

logger = logging.getLogger(__name__)

# 同步间隔：10 分钟；覆盖 45 页全量（含 raw-ledger 近 2 万条等大表），
# 单轮可能耗时数分钟，超时放宽到 1 小时，避免大表同步被中断
_WAREHOUSE_SYNC_INTERVAL_SECONDS = 600
_WAREHOUSE_SYNC_TIMEOUT_SECONDS = 3600


async def _run_warehouse_sync() -> None:
    """增量同步全部飞书页面（45 页）+ 三张库存表（AI 分析数据源）。

    单页失败由 service 内部 try/except + logger.exception 隔离，不阻断整轮。
    增量按 source_record_id upsert + 软删，重复执行幂等。
    """
    try:
        async with async_session_factory() as session:
            service = WarehouseService(session)
            for page_key in FEISHU_WAREHOUSE_MATERIAL_PAGES:
                try:
                    await service.sync_material_page_to_local(page_key)
                except Exception:
                    logger.exception(
                        "warehouse page sync failed (scheduled)",
                        extra={"page": page_key},
                    )
            await service.sync_inventory_from_feishu()
            await session.commit()
            logger.info("warehouse scheduled sync completed")
    except Exception:
        logger.exception("warehouse scheduled sync failed")


warehouse_sync_task = TaskDefinition(
    name="warehouse.feishu_incremental_sync",
    schedule=ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=_WAREHOUSE_SYNC_INTERVAL_SECONDS,
    ),
    coro=_run_warehouse_sync,
    timeout_seconds=_WAREHOUSE_SYNC_TIMEOUT_SECONDS,
    module="warehouse",
)
