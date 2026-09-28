"""生产计划/产销计划/FL 批次月表飞书表定时自动同步。

对齐仓储同步机制：每 10 分钟全天高频同步一次（INTERVAL，小表全量
upsert，删除/修改每轮都对齐，无 8-20 点小时 cron 的夜间空窗）；
飞书多维表格记录变更另有 WebSocket 长连接（production/ws_client.py）
秒级触发同步，10 分钟轮次作为其兜底。页面手动同步不受影响。
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


class ProductionPlanFeishuSyncGenerator(TaskGenerator):
    name = "production.plan_feishu_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=600,  # 对齐仓储：10 分钟高频节拍
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: Any) -> list[str]:
        """返回需要同步的启用中的生产计划/产销计划/FL 批次月表配置 ID。"""
        result = await session.execute(
            select(ProductionFeishuConfig.id).where(
                ProductionFeishuConfig.is_active.is_(True),
                ProductionFeishuConfig.is_deleted.is_(False),
                # 销售计划无独立定时器，与生产计划同节拍对齐飞书；
                # FL 批次月表与生产计划同节拍自动同步
                ProductionFeishuConfig.sync_target.in_(
                    ("production_plan", "sales_plan", "fl_batch")
                ),
            )
        )
        return [str(value) for value in result.scalars().all()]

    async def execute_one(self, session: Any, item: Any) -> None:
        config = await session.get(ProductionFeishuConfig, UUID(str(item)))
        if config is None:
            return
        await sync_config_by_target(config, session)
