"""安全模块定时任务（平台调度器接入）。

- 法规雷达：每周一 08:00（北京时间）自动扫描一次，手动触发走 API。
- 页面镜像同步：每 15 分钟同步启用的镜像页（本地全量副本），
  手动触发走「安全飞书设置」页的立即同步按钮。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from app.modules.safety.models import SafetyPageFeishuConfig
from app.modules.safety.service import page_table, regulation_radar
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger(__name__)

MIRROR_SYNC_INTERVAL = timedelta(minutes=15)


class SafetyRegulationRadarGenerator(TaskGenerator):
    """每周一 08:00 扫描官方栏目页，发现新法规与已修订法规。"""

    name = "safety.regulation_radar_weekly"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        # 分 时 日 月 周 —— 每周一 08:00
        expression="0 8 * * 1",
        timezone="Asia/Shanghai",
    )
    # 抓取 5 个站点 + AI 过滤 + 写入飞书，放宽超时
    timeout_seconds = 1800

    async def find_due(self, session: Any) -> list[Any]:
        # 尊重设置页的「自动扫描」开关（safety.feishu_app_settings.radar_scan_enabled）
        from app.modules.safety.models import SafetyFeishuAppSettings

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.radar_scan_enabled:
            logger.info("法规雷达自动扫描已关闭（radar_scan_enabled=false），本轮跳过")
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        result = await regulation_radar.run_radar(
            session, dry_run=False, trigger="schedule"
        )
        logger.info(
            "法规雷达周扫完成: 状态=%s 新=%s 修订=%s 跳过=%s 错误=%s",
            result.get("status"),
            result.get("new_count"),
            result.get("revised_count"),
            result.get("skipped_count"),
            len(result.get("errors", [])),
        )


class SafetyPageMirrorSyncGenerator(TaskGenerator):
    """每 15 分钟同步启用的页面镜像（飞书多维表格 → 本地全量副本）。

    只挑「绑定完整、镜像开启、距上次同步超过间隔」的页面；同步失败
    状态回写绑定行，不影响其他页面。手动触发走设置页「立即同步」。
    """

    name = "safety.page_table_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=int(MIRROR_SYNC_INTERVAL.total_seconds()),
        timezone="Asia/Shanghai",
    )
    # 全量翻页拉取大表可能较慢，放宽超时
    timeout_seconds = 30 * 60

    async def find_due(self, session: Any) -> list[Any]:
        cutoff = datetime.now(UTC) - MIRROR_SYNC_INTERVAL
        result = await session.execute(
            select(SafetyPageFeishuConfig.page_key).where(
                SafetyPageFeishuConfig.is_deleted.is_(False),
                SafetyPageFeishuConfig.is_enabled.is_(True),
                SafetyPageFeishuConfig.is_mirrored.is_(True),
                SafetyPageFeishuConfig.app_token.isnot(None),
                SafetyPageFeishuConfig.table_id.isnot(None),
                or_(
                    SafetyPageFeishuConfig.last_synced_at.is_(None),
                    SafetyPageFeishuConfig.last_synced_at <= cutoff,
                ),
            )
        )
        return [str(key) for key in result.scalars().all()]

    async def execute_one(self, session: Any, item: Any) -> None:
        page_key = str(item)
        count = await page_table.sync_page_table_mirror(session, page_key)
        logger.info("页面镜像定时同步完成: page=%s 记录=%s", page_key, count)
