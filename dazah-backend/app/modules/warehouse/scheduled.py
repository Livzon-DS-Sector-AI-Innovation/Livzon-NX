"""Warehouse scheduled sync task — periodic feishu → local sync.

高频增量（10 分钟）：按日期字段降序只拉变更/新增，大表秒级；
低频全量（每天一次）：全量拉取兜底，保证删除/历史修改一致。
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import async_session_factory
from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.modules.warehouse.service import WarehouseService
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskDefinition

logger = logging.getLogger(__name__)

# 高频增量同步间隔：10 分钟（增量按日期字段只拉变更，单轮通常秒级）
_WAREHOUSE_SYNC_INTERVAL_SECONDS = 600
_WAREHOUSE_SYNC_TIMEOUT_SECONDS = 3600

# 每天全量兜底：北京时间 00:00（无人操作时段），保证删除/历史修改一致
_WAREHOUSE_FULL_SYNC_TIMEOUT_SECONDS = 7200

# 全量兜底执行窗口（北京时间 00:00-06:00，不含 06:00）：
# FIXED_TIME 语义是"当天 00:00 已过即触发"，若后端在 00:00 后（如中午）重启会误触发，
# 因此用窗口限定只在该时段执行，错过窗口则等次日凌晨。
_FULL_SYNC_WINDOW_START_HOUR = 0
_FULL_SYNC_WINDOW_END_HOUR = 6


def _in_full_sync_window(now_cn: datetime) -> bool:
    """判断北京时间 now 是否处于全量兜底凌晨窗口内。"""
    return _FULL_SYNC_WINDOW_START_HOUR <= now_cn.hour < _FULL_SYNC_WINDOW_END_HOUR


# 全量同步运行标志：全量执行期间，高频增量跳过本轮，避免同时写本地快照竞争
_full_sync_running = False


async def _run_warehouse_sync() -> None:
    """高频增量同步全部飞书页面 + 三张库存表（AI 分析数据源）。

    增量按日期字段降序只拉上次同步后的变更/新增（秒级），
    单页失败由 service 内部 try/except 隔离，不阻断整轮。
    全量兜底执行期间跳过本轮，避免与全量写库竞争。
    """
    global _full_sync_running
    if _full_sync_running:
        logger.info("warehouse full sync in progress, skip incremental round")
        return
    try:
        async with async_session_factory() as session:
            service = WarehouseService(session)
            for page_key in FEISHU_WAREHOUSE_MATERIAL_PAGES:
                try:
                    await service.sync_material_page_to_local(
                        page_key, incremental=True
                    )
                except Exception:
                    logger.exception(
                        "warehouse page incremental sync failed (scheduled)",
                        extra={"page": page_key},
                    )
            await service.sync_inventory_from_feishu()
            await session.commit()
            logger.info("warehouse scheduled incremental sync completed")
    except Exception:
        logger.exception("warehouse scheduled sync failed")


async def _run_warehouse_full_sync() -> None:
    """低频全量兜底同步：全量拉取 + 软删清理，保证删除/历史修改一致。

    只全量 material-page 台账（含大表），库存表由高频任务负责。
    仅在凌晨窗口（北京 00:00-06:00）执行；错过窗口则跳过，等次日凌晨。
    """
    global _full_sync_running
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    if not _in_full_sync_window(now_cn):
        logger.info(
            "warehouse full sync skipped: outside 00:00-06:00 Beijing window (now=%s)",
            now_cn.isoformat(timespec="minutes"),
        )
        return
    _full_sync_running = True
    try:
        async with async_session_factory() as session:
            service = WarehouseService(session)
            for page_key in FEISHU_WAREHOUSE_MATERIAL_PAGES:
                try:
                    await service.sync_material_page_to_local(
                        page_key, incremental=False
                    )
                except Exception:
                    logger.exception(
                        "warehouse page full sync failed (scheduled)",
                        extra={"page": page_key},
                    )
            await session.commit()
            logger.info("warehouse scheduled full sync completed")
    except Exception:
        logger.exception("warehouse scheduled full sync failed")
    finally:
        _full_sync_running = False


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

warehouse_full_sync_task = TaskDefinition(
    name="warehouse.feishu_full_sync",
    schedule=ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="00:00",
        timezone="Asia/Shanghai",
    ),
    coro=_run_warehouse_full_sync,
    timeout_seconds=_WAREHOUSE_FULL_SYNC_TIMEOUT_SECONDS,
    module="warehouse",
)
