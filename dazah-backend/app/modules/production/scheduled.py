"""生产计划/销售计划飞书表定时自动同步。

北京时间每天 8:00-20:00 每小时整点自动同步一次（cron 8-20 点），
其余时段（20:00-次日 8:00）仅支持页面手动同步。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.production.production_feishu_models import ProductionFeishuConfig
from app.modules.production.production_plan_service import sync_config_by_target
from app.platform.scheduler import (
    ScheduleConfig,
    ScheduleStrategy,
    TaskGenerator,
)


class ProductionPlanHourlySyncGenerator(TaskGenerator):
    name = "production.plan_feishu_hourly_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        expression="0 8-20 * * *",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: Any) -> list[str]:
        """返回需要同步的启用中的生产计划/销售计划飞书配置 ID。"""
        result = await session.execute(
            select(ProductionFeishuConfig.id).where(
                ProductionFeishuConfig.is_active.is_(True),
                ProductionFeishuConfig.is_deleted.is_(False),
                # 销售计划无独立定时器，与生产计划同时段每小时对齐飞书
                ProductionFeishuConfig.sync_target.in_(
                    ("production_plan", "sales_plan")
                ),
            )
        )
        return [str(value) for value in result.scalars().all()]

    async def execute_one(self, session: Any, item: Any) -> None:
        config = await session.get(ProductionFeishuConfig, UUID(str(item)))
        if config is None:
            return
        await sync_config_by_target(config, session)
