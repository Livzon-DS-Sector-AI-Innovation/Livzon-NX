"""趋势 AI 月度定时分析：每月指定日对所有已启用产品线全量分析并发送。

由 TrendAlertMonthlyAnalysisGenerator（每日 09:00 检查一次）驱动：
当天日期 ≥ 通知设置的 monthly_day（默认 25 日，月底不足取当月最后一天）
且当月尚未跑过时，遍历全部产品线趋势仪表盘数据（enable_trend_ai=True），
复用页面路径触发产品级月度AI——一个产品一次分析、一张合并卡（全部指标
合并，硬编码防飞书卡片限流），必定发送，不受手动重分析开关影响。
"""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.trend_monthly_run import QualityTrendMonthlyRun
from app.modules.quality.service.inspection_dashboard_entry import (
    get_bbas_dashboard_data,
    get_dls_dashboard_data,
    get_formulations_dashboard_data,
    get_lft_dashboard_data,
    get_lkms_dashboard_data,
    get_mpa_dashboard_data,
    get_mvt_dashboard_data,
    get_tryptophan_dashboard_data,
    get_water_dashboard_data,
)
from app.modules.quality.service.quality_notification_settings import (
    load_inspection_trend_alert_config,
)

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Shanghai")

# 与 api/inspection_feishu.py 的分组入口保持一致
_GROUP_RUNNERS: list[tuple[str, Any, dict[str, Any]]] = [
    ("mpa", get_mpa_dashboard_data, {}),
    ("mvt", get_mvt_dashboard_data, {}),
    ("lft", get_lft_dashboard_data, {}),
    ("dls", get_dls_dashboard_data, {}),
    ("lkms", get_lkms_dashboard_data, {}),
    ("bbas", get_bbas_dashboard_data, {}),
    ("tryptophan", get_tryptophan_dashboard_data, {}),
    ("formulations", get_formulations_dashboard_data, {}),
    ("water", get_water_dashboard_data, {}),
]


async def find_due_trend_monthly_analysis(db: AsyncSession) -> list[str]:
    """当天已到 monthly_day 且当月未跑过 → 返回 [period] 触发执行。"""
    config = await load_inspection_trend_alert_config(db)
    if not config.is_enabled:
        return []
    now = datetime.now(_TZ)
    period = now.strftime("%Y-%m")
    existing = await db.execute(
        select(QualityTrendMonthlyRun.id).where(
            QualityTrendMonthlyRun.period == period,
            QualityTrendMonthlyRun.is_deleted.is_(False),
        )
    )
    if existing.first() is not None:
        return []
    last_day = calendar.monthrange(now.year, now.month)[1]
    effective_day = min(config.monthly_day, last_day)
    if now.day < effective_day:
        return []
    return [period]


async def run_trend_monthly_analysis(
    db: AsyncSession, period: str
) -> dict[str, Any]:
    """执行一个月度周期的全量分析入队；完成后标记 done。"""
    existing = await db.execute(
        select(QualityTrendMonthlyRun).where(
            QualityTrendMonthlyRun.period == period,
            QualityTrendMonthlyRun.is_deleted.is_(False),
        )
    )
    if existing.scalars().first() is not None:
        return {"status": "already"}

    run_row = QualityTrendMonthlyRun(
        period=period,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run_row)
    await db.commit()

    config = await load_inspection_trend_alert_config(db)
    stats: dict[str, Any] = {"lines": 0, "charts": 0, "enqueued": 0, "skipped": 0}
    for _group, entry, kwargs in _GROUP_RUNNERS:
        try:
            # enable_trend_ai=True：产品级月度AI在页面路径内自动建行并提交
            # job（一个产品一次分析、一张合并卡），无指标命中则不触发
            result = await entry(
                db,
                sender_user_open_id=None,
                frontend_group=_group,
                enable_trend_ai=True,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 —— 单组失败不阻塞其余产品线
            logger.warning("月度分析拉取 %s 失败: %s", _group, type(exc).__name__)
            stats["skipped"] += 1
            continue
        if not result.get("configured"):
            continue
        line_config = config.lines.get(result["source_entity_code"]) or {}
        if not line_config.get("enabled", True):
            continue
        stats["lines"] += 1
        summary = result.get("summary") or {}
        charts = result.get("charts") or []
        stats["charts"] += len(charts)
        if summary.get("trend_ai_pending_count") or summary.get(
            "trend_ai_completed_count"
        ):
            # 该产品线当月命中判据并已触发产品级合并分析（一行/一卡）
            stats["enqueued"] += 1

    run_row.status = "done"
    run_row.finished_at = datetime.now(UTC)
    run_row.last_error = (
        f"{stats['skipped']} 组拉取失败" if stats["skipped"] else None
    )
    await db.commit()
    logger.info(
        "趋势 AI 月度分析完成 %s: %s 条产品线入队（产品级合并，一个产品一张卡）",
        period,
        stats["enqueued"],
    )
    return stats
