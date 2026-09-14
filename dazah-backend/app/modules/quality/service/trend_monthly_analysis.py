"""趋势 AI 月度定时分析：每月指定日对全部产品线全量分析并按 AI 终审推送。

由 TrendAlertMonthlyAnalysisGenerator（每日 09:00 检查一次）驱动：
当天日期 ≥ 通知设置的 monthly_day（默认 25 日，月底不足取当月最后一天）
且当月尚未跑过时，遍历**全部 15 条产品线目录**（FINISHED_DASHBOARD_LINE_CATALOG，
逐 entity_code 而非只跑各入口默认线）拉取仪表盘数据（enable_trend_ai=True），
复用页面路径：粗筛提名 → 产品级一次 AI 终审 → 只对判定异常的指标发一张
合并卡（含各指标趋势图），全部正常的产品线不发卡。
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.trend_monthly_run import QualityTrendMonthlyRun
from app.modules.quality.service import inspection_dashboard_calc as calc
from app.modules.quality.service.inspection_dashboard_config import (
    BBAS_FCC14_DASHBOARD_ENTITY_CODE,
    BBAS_HANGUANG_K1_DASHBOARD_ENTITY_CODE,
    DLS_GB_DASHBOARD_ENTITY_CODE,
    DLS_VET_DASHBOARD_ENTITY_CODE,
    FINISHED_DASHBOARD_LINE_CATALOG,
    FORMULATIONS_FEN_DASHBOARD_ENTITY_CODE,
    FORMULATIONS_FLU_DASHBOARD_ENTITY_CODE,
    LFT_EP_DASHBOARD_ENTITY_CODE,
    LFT_USP_DASHBOARD_ENTITY_CODE,
    LKMS_VET_DASHBOARD_ENTITY_CODE,
    MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE,
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE,
    MVT_DASHBOARD_ENTITY_CODE,
    TRYPTOPHAN_GRANULE_DASHBOARD_ENTITY_CODE,
    TRYPTOPHAN_POWDER_DASHBOARD_ENTITY_CODE,
    WATER_PURE_DASHBOARD_ENTITY_CODE,
)
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

# entity_code → 分组入口（与 api/inspection_feishu.py 的分组入口一致）。
# 必须逐 entity_code 跑：同一入口的备选线（高规/USP/兽药/K1/色氨酸粉末/芬苯达唑）
# 不能只靠入口默认值覆盖，否则这些产品线永远拿不到月度分析。
_ENTITY_GROUP_MAP: dict[str, str] = {
    MPA_INTERNAL_DASHBOARD_ENTITY_CODE: "mpa",
    MPA_HIGH_SPEC_DASHBOARD_ENTITY_CODE: "mpa",
    MVT_DASHBOARD_ENTITY_CODE: "mvt",
    LFT_EP_DASHBOARD_ENTITY_CODE: "lft",
    LFT_USP_DASHBOARD_ENTITY_CODE: "lft",
    DLS_GB_DASHBOARD_ENTITY_CODE: "dls",
    DLS_VET_DASHBOARD_ENTITY_CODE: "dls",
    LKMS_VET_DASHBOARD_ENTITY_CODE: "lkms",
    BBAS_FCC14_DASHBOARD_ENTITY_CODE: "bbas",
    BBAS_HANGUANG_K1_DASHBOARD_ENTITY_CODE: "bbas",
    TRYPTOPHAN_POWDER_DASHBOARD_ENTITY_CODE: "tryptophan",
    TRYPTOPHAN_GRANULE_DASHBOARD_ENTITY_CODE: "tryptophan",
    FORMULATIONS_FLU_DASHBOARD_ENTITY_CODE: "formulations",
    FORMULATIONS_FEN_DASHBOARD_ENTITY_CODE: "formulations",
    WATER_PURE_DASHBOARD_ENTITY_CODE: "water",
}

_GROUP_ENTRIES: dict[str, Any] = {
    "mpa": get_mpa_dashboard_data,
    "mvt": get_mvt_dashboard_data,
    "lft": get_lft_dashboard_data,
    "dls": get_dls_dashboard_data,
    "lkms": get_lkms_dashboard_data,
    "bbas": get_bbas_dashboard_data,
    "tryptophan": get_tryptophan_dashboard_data,
    "formulations": get_formulations_dashboard_data,
    "water": get_water_dashboard_data,
}


def resolve_line_group(entity_code: str) -> str | None:
    """产品线 entity_code → 分组入口键；未匹配返回 None。"""
    return _ENTITY_GROUP_MAP.get(entity_code)


def iter_monthly_lines() -> list[tuple[str, str, Any]]:
    """月度分析产品线清单：[(entity_code, 展示名, 入口函数)]，覆盖全部目录线。"""
    lines: list[tuple[str, str, Any]] = []
    for entity_code, label in FINISHED_DASHBOARD_LINE_CATALOG:
        entry = _GROUP_ENTRIES.get(str(resolve_line_group(entity_code) or ""))
        if entry is None:
            logger.warning(
                "月度分析跳过未登记分组的产品线：%s（%s）", entity_code, label
            )
            continue
        lines.append((entity_code, label, entry))
    return lines


# 无人值守可靠性：逐线等待产品级 AI 任务到达终态（串行 = 上游不限流、连接池不吃紧）；
# 任务因限流/超时失败时自动重试，避免月度卡片整条线漏发。
_LINE_JOB_POLL_SECONDS = 5
_LINE_JOB_WAIT_TIMEOUT = 900
_LINE_JOB_MAX_ATTEMPTS = 2


async def _wait_line_ai_job(
    db: AsyncSession,
    *,
    entity_code: str,
    period: str,
) -> str:
    """等待产品线当月产品级 AI 任务到达终态；failed/ai_failed 无结论则重试一次。

    返回最终状态（none/终态名/timeout/exhausted）。轮询前 expire_all 以读到
    任务进程写入数据库的最新状态。
    """
    for attempt in range(_LINE_JOB_MAX_ATTEMPTS):
        deadline = time.monotonic() + _LINE_JOB_WAIT_TIMEOUT
        while True:
            db.expire_all()
            row = await calc._get_existing_trend_ai(
                db,
                entity_code=entity_code,
                metric_key=calc.TREND_PRODUCT_METRIC_KEY,
                rule_type=calc.TREND_OVERALL_RULE,
                trend_end_batch=period,
            )
            if row is None:
                return "none"
            status = str(row.notification_status or "")
            if status != "pending":
                if (
                    status in {"failed", "ai_failed"}
                    and not row.ai_summary
                    and attempt + 1 < _LINE_JOB_MAX_ATTEMPTS
                ):
                    logger.warning(
                        "月度分析 %s 任务状态 %s，自动重试（第 %s 次）",
                        entity_code,
                        status,
                        attempt + 2,
                    )
                    await calc._submit_trend_ai_job(row, sender_user_open_id=None)
                    await db.commit()
                    break
                return status
            if time.monotonic() >= deadline:
                return "timeout"
            await asyncio.sleep(_LINE_JOB_POLL_SECONDS)
    return "exhausted"


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
    for entity_code, label, entry in iter_monthly_lines():
        line_config = config.lines.get(entity_code) or {}
        if not line_config.get("enabled", True):
            continue  # 通知设置里停用的产品线不跑
        try:
            # enable_trend_ai=True：产品级月度AI在页面路径内自动建行并提交
            # job（粗筛 → AI 终审 → 只对真异常发一张合并卡）
            result = await entry(
                db,
                sender_user_open_id=None,
                frontend_group=resolve_line_group(entity_code) or "",
                source_entity_code=entity_code,
                enable_trend_ai=True,
            )
        except Exception as exc:  # noqa: BLE001 —— 单线失败不阻塞其余产品线
            logger.warning(
                "月度分析拉取 %s（%s）失败: %s", entity_code, label, type(exc).__name__
            )
            stats["skipped"] += 1
            continue
        if not result.get("configured"):
            continue
        stats["lines"] += 1
        summary = result.get("summary") or {}
        charts = result.get("charts") or []
        stats["charts"] += len(charts)
        if summary.get("trend_ai_pending_count") or summary.get(
            "trend_ai_completed_count"
        ):
            # 该产品线当月已触发产品级 AI 终审（是否推卡由终审裁决决定）
            stats["enqueued"] += 1
            # 串行等待到终态（失败自动重试），再进入下一条产品线
            final_status = await _wait_line_ai_job(
                db, entity_code=entity_code, period=period
            )
            if final_status in {"failed", "ai_failed", "timeout", "exhausted"}:
                stats["skipped"] += 1
                logger.warning("月度分析 %s 未成功：%s", entity_code, final_status)

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
