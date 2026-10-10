"""设备巡检飞书镜像同步调度器。

增量：每 5 分钟按水位同步三张表（今日巡检 / 历史记录 / 设备档案）；
全量：每天 03:10 全表对账（补漏 + 删除对账）。未配置时静默跳过。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.service import inspection_feishu_config as feishu_config
from app.modules.equipment.service import inspection_feishu_mirror as mirror
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger(__name__)


class InspectionFeishuMirrorSyncGenerator(TaskGenerator):
    """每 5 分钟增量同步设备巡检飞书多维表格镜像。"""

    name = "equipment.inspection_feishu_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=300,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: AsyncSession) -> list[Any]:
        if not await feishu_config.is_mirror_enabled(session):
            return []
        return ["all"]

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        results = await mirror.sync_all(session, incremental=True)
        await session.commit()
        logger.info("inspection feishu mirror incremental sync: %s", results)


class InspectionFeishuMirrorFullSyncGenerator(TaskGenerator):
    """每天 03:10 全量对账（补漏 + 删除飞书侧已删行）。"""

    name = "equipment.inspection_feishu_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="03:10",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: AsyncSession) -> list[Any]:
        if not await feishu_config.is_mirror_enabled(session):
            return []
        return ["all"]

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        results = await mirror.sync_all(session, incremental=False)
        await session.commit()
        logger.info("inspection feishu mirror full sync: %s", results)
