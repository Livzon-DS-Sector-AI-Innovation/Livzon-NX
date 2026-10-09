"""法规雷达定时任务（平台调度器接入）。

每周一 08:00（北京时间）自动扫描一次。手动触发走 API 端点，
两者共用 regulation_radar.run_radar。
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.safety.service import regulation_radar
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger(__name__)


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
        # 无条件触发：雷达是数据发现底座，不受通知开关控制
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
