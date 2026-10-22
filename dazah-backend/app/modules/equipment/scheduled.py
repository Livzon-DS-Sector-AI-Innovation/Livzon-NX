"""设备巡检飞书镜像同步调度器。

增量：每 5 分钟按水位同步各启用车间三张表（今日巡检 / 历史记录 /
设备档案）；全量：每天 03:10 全表对账（补漏 + 删除对账）。
每个启用车间一个任务项，单车间失败不影响其他车间。未配置的
车间静默跳过。
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
    """每 5 分钟增量同步各车间设备巡检飞书多维表格镜像。"""

    name = "equipment.inspection_feishu_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=300,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: AsyncSession) -> list[Any]:
        return await feishu_config.list_enabled_workshops(session)

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        workshop_code = str(item)
        results = await mirror.sync_all(session, workshop_code, incremental=True)
        await session.commit()
        logger.info(
            "inspection feishu mirror incremental sync [%s]: %s",
            workshop_code,
            results,
        )


class InspectionFeishuMirrorFullSyncGenerator(TaskGenerator):
    """每天 03:10 各启用车间全量对账（补漏 + 删除飞书侧已删行）。"""

    name = "equipment.inspection_feishu_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="03:10",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: AsyncSession) -> list[Any]:
        return await feishu_config.list_enabled_workshops(session)

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        workshop_code = str(item)
        results = await mirror.sync_all(session, workshop_code, incremental=False)
        await session.commit()
        logger.info(
            "inspection feishu mirror full sync [%s]: %s",
            workshop_code,
            results,
        )


class SparePartHardwareSyncGenerator(TaskGenerator):
    """每小时把仓储五金镜像同步到设备备件台账（按车间聚合批次）。"""

    name = "equipment.spare_part_hardware_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: AsyncSession) -> list[Any]:
        return ["all"]

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        from app.modules.equipment.service import spare_part_sync

        results = await spare_part_sync.sync_all(session)
        await session.commit()
        logger.info("spare part hardware sync: %s", results)
