"""Scheduled generators for regulatory tracker.

执行时序（北京时间），抓取 / AI 分析 / 推送拆成三个独立任务，
避免单次任务超时（默认 300s）拖垮整条链路：

1. 00:10 夜间抓取：遍历所有法规站点增量入库（站点级并发 + 单站硬超时），
   不发送推送、不内置 AI 分析；
2. 02:00 AI 分析：对近 50 篇未分析文档执行 LLM 筛选与摘要（推送前完成）；
3. 10:00 定时推送：把近 ``recent_days`` 天新增/更新的已接受文档推送给
   配置的 QA 接收人（按 content_hash 去重）。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.services.ai_analysis_service import (
    analyze_new_documents,
)
from app.modules.regulatory_tracker.services.notification_service import (
    RegulatoryTrackerNotificationService,
)
from app.modules.regulatory_tracker.services.sync_service import run_all_sites
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger(__name__)

# 抓取 10+ 个站点，默认 300 秒不够（实测单站点可挂起 45s+），放宽到 30 分钟
_SYNC_TIMEOUT_SECONDS = 1800
# 02:00 AI 分析单次上限：夜间增量通常远小于 50 篇，且按未分析状态天然增量
_ANALYSIS_LIMIT = 50
# 夜间抓取回看窗口：凌晨跑任务时用 2 天覆盖前一日内容，防漏
_NIGHTLY_SYNC_RECENT_DAYS = 2


class RegulatoryTrackerNightlySyncGenerator(TaskGenerator):
    """每天凌晨 00:10 抓取法规更新入库（不含分析、不含推送）。"""

    name = "regulatory_tracker.nightly_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="00:10",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = _SYNC_TIMEOUT_SECONDS

    async def find_due(self, session: Any) -> list[Any]:
        # 无条件触发：抓取是数据底座，不应被通知开关关闭
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        result = await run_all_sites(
            session,
            recent_days=_NIGHTLY_SYNC_RECENT_DAYS,
            analyze=False,
        )
        logger.info(
            "法规夜间抓取完成: checked=%s new=%s updated=%s",
            result.get("totals", {}).get("checked"),
            result.get("totals", {}).get("inserted"),
            result.get("totals", {}).get("updated"),
        )


class RegulatoryTrackerDailyAnalysisGenerator(TaskGenerator):
    """每天 02:00 对未分析的法规文档执行 AI 分析（晚于夜间抓取，早于推送）。"""

    name = "regulatory_tracker.daily_analysis"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:00",
        timezone="Asia/Shanghai",
    )
    # AI 分析可能较慢，放宽超时上限
    timeout_seconds = 1800

    async def find_due(self, session: Any) -> list[Any]:
        # 无条件触发，返回哨兵项使 execute_one 执行一次
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        stats = await analyze_new_documents(session, limit=_ANALYSIS_LIMIT)
        logger.info(
            "✅ 法规文档 AI 每日分析完成: analyzed=%d failed=%d skipped=%d",
            stats.get("analyzed", 0),
            stats.get("failed", 0),
            stats.get("skipped", 0),
        )


class RegulatoryTrackerDailyNotifyGenerator(TaskGenerator):
    """每天 10:00 把近 N 天新增/更新的法规推送通知给配置的 QA 接收人。"""

    name = "regulatory_tracker.daily_notify"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="10:00",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 600

    async def find_due(self, session: Any) -> list[Any]:
        setting = await repo.get_notification_setting(session)
        if (
            setting is None
            or not setting.is_enabled
            or not (setting.recipient_open_id or "").strip()
        ):
            return []
        return [setting]

    async def execute_one(self, session: Any, item: Any) -> None:
        threshold = date.today() - timedelta(days=max(item.recent_days - 1, 0))
        document_ids = await repo.list_recent_accepted_document_ids(
            session,
            threshold=threshold,
        )
        result = await RegulatoryTrackerNotificationService(
            session
        ).send_update_notifications(
            document_ids=[str(document_id) for document_id in document_ids],
            trigger_type="daily_auto_sync",
        )
        logger.info(
            "法规定时推送完成: sent=%d skipped=%d failed=%d",
            result.get("sent", 0),
            result.get("skipped", 0),
            result.get("failed", 0),
        )
