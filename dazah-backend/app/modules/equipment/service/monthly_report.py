"""设备月度健康报告：SQL 聚合指标 + LLM 叙述。

设计约束：
- 所有数字来自 SQL 聚合，LLM 只负责把数字组织成可读叙述
  （chat + response_format=None，Markdown 输出）；
- LLM 失败时报告仍落库（数据 + 占位说明），不阻塞生成。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.health import (
    EquipmentHealthSnapshot,
    EquipmentMonthlyReport,
)
from app.modules.equipment.models.work_order import WorkOrder

logger = logging.getLogger(__name__)


def _month_bounds(report_month: str) -> tuple[date, date]:
    """'YYYY-MM' → (起日, 止日)。"""
    try:
        year, month = (int(x) for x in report_month.split("-"))
    except ValueError as e:
        raise AppException(message="月份格式必须为 YYYY-MM") from e
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


async def aggregate_monthly_metrics(
    db: AsyncSession, report_month: str
) -> dict[str, Any]:
    """聚合当月指标（工单/故障/时长/红黄设备/车间分布）。"""
    start, end = _month_bounds(report_month)

    orders = (
        (
            await db.execute(
                select(WorkOrder)
                .options(selectinload(WorkOrder.equipment))
                .where(
                    WorkOrder.reported_at >= start,
                    WorkOrder.reported_at < end,
                    WorkOrder.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    faults = [o for o in orders if o.order_type == "故障维修"]
    durations = [o.actual_duration or 0 for o in faults if o.actual_duration]
    mttr = round(sum(durations) / len(durations), 1) if durations else None

    # 当月最后一天的健康快照分档分布
    snapshot_stats = (
        await db.execute(
            select(
                EquipmentHealthSnapshot.grade,
                func.count(EquipmentHealthSnapshot.id),
            )
            .where(
                EquipmentHealthSnapshot.snapshot_date >= start,
                EquipmentHealthSnapshot.snapshot_date < end,
                EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
            )
            .group_by(EquipmentHealthSnapshot.grade)
        )
    ).all()
    # 取每月每天分档计数中的最大红档数（近似月末状态）
    grade_totals = {g: int(c) for g, c in snapshot_stats}

    # 故障 TOP5 设备
    fault_by_equipment: dict[str, int] = {}
    for o in faults:
        eq = o.equipment
        name = eq.name if eq else "未知设备"
        fault_by_equipment[name] = fault_by_equipment.get(name, 0) + 1
    top_faults = sorted(
        fault_by_equipment.items(), key=lambda x: x[1], reverse=True
    )[:5]

    return {
        "month": report_month,
        "total_orders": len(orders),
        "fault_orders": len(faults),
        "mttr_min": mttr,
        "open_orders": sum(
            1 for o in orders if o.status in ("待处理", "执行中", "待验收")
        ),
        "grade_totals": grade_totals,
        "top_fault_equipment": [
            {"name": n, "count": c} for n, c in top_faults
        ],
        "equipment_total": (
            (
                await db.execute(
                    select(func.count())
                    .select_from(Equipment)
                    .where(
                        Equipment.status.in_(["在用", "备用"]),
                        Equipment.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one()
        ),
    }


async def generate_monthly_report(
    db: AsyncSession,
    report_month: str,
    operator_id: Any = None,
) -> EquipmentMonthlyReport:
    """生成（或覆盖重生成）指定月份报告。"""
    metrics = await aggregate_monthly_metrics(db, report_month)
    content_md = await _render_narrative(metrics)

    report = (
        (
            await db.execute(
                select(EquipmentMonthlyReport).where(
                    EquipmentMonthlyReport.report_month == report_month,
                    EquipmentMonthlyReport.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if report is None:
        report = EquipmentMonthlyReport(report_month=report_month)
        if operator_id is not None:
            report.created_by = operator_id
        db.add(report)
    report.metrics = metrics
    report.content_md = content_md
    report.updated_by = operator_id
    await db.flush()
    return report


async def _render_narrative(metrics: dict[str, Any]) -> str:
    """LLM 把聚合数字组织成 Markdown 叙述；失败回落模板文本。"""
    import json

    from app.core.llm import LLMError, llm_client

    prompt = (
        "你是制药工厂设备管理月报撰写助手。以下 JSON 是本月设备运行聚合数据"
        "（数字已由系统统计完成，禁止改写或推算数字）。"
        "请输出一份简明的中文 Markdown 月报，结构：## 总体情况 / ## 故障分析 /"
        " ## 健康度 / ## 下月建议。只做叙述与归纳，不虚构任何数字。\n\n"
        f"{json.dumps(metrics, ensure_ascii=False, default=str)}"
    )
    try:
        content = await llm_client.chat(
            [
                {
                    "role": "system",
                    "content": "你是设备管理月报撰写助手，输出 Markdown。",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=None,
            temperature=0.2,
            timeout=60,
        )
        text = str(content).strip()
        if text:
            return text
        logger.info("月报 LLM 叙述返回为空，回落模板文本")
    except LLMError:
        logger.info("月报 LLM 叙述未生效，回落模板文本")
    except Exception:
        logger.warning("月报 LLM 叙述失败，回落模板文本", exc_info=True)
    return _fallback_narrative(metrics)


def _fallback_narrative(metrics: dict[str, Any]) -> str:
    top = metrics.get("top_fault_equipment") or []
    top_lines = "\n".join(
        f"- {item['name']}：{item['count']} 次" for item in top
    ) or "- 本月无故障工单"
    grades = metrics.get("grade_totals") or {}
    mttr = metrics.get("mttr_min")
    return (
        f"## 总体情况\n\n"
        f"本月新增工单 {metrics.get('total_orders', 0)} 单"
        f"（其中故障维修 {metrics.get('fault_orders', 0)} 单），"
        f"未闭环 {metrics.get('open_orders', 0)} 单；"
        f"平均修复时长 {f'{mttr} 分钟' if mttr is not None else '暂无数据'}。\n\n"
        f"## 故障分析\n\n{top_lines}\n\n"
        f"## 健康度\n\n"
        f"本月快照分档累计：红 {grades.get('R', 0)}、黄 {grades.get('Y', 0)}、"
        f"绿 {grades.get('G', 0)}"
        f"（设备共 {metrics.get('equipment_total', 0)} 台）。\n\n"
        f"## 下月建议\n\n"
        f"- 重点关注故障高频设备的保养计划执行情况\n"
        f"- 核查红/黄档设备的超期保养与校准项\n\n"
        f"> 本报告由系统聚合生成；叙述部分当前为模板文本（LLM 未启用）。\n"
    )


async def get_monthly_report(
    db: AsyncSession, report_month: str
) -> EquipmentMonthlyReport:
    report = (
        (
            await db.execute(
                select(EquipmentMonthlyReport).where(
                    EquipmentMonthlyReport.report_month == report_month,
                    EquipmentMonthlyReport.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if report is None:
        raise AppException(message=f"{report_month} 月度报告尚未生成")
    return report


async def list_monthly_reports(
    db: AsyncSession,
) -> list[EquipmentMonthlyReport]:
    rows = (
        (
            await db.execute(
                select(EquipmentMonthlyReport)
                .where(
                    EquipmentMonthlyReport.is_deleted == False  # noqa: E712
                )
                .order_by(EquipmentMonthlyReport.report_month.desc())
                .limit(24)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def previous_month(today: date | None = None) -> str:
    """返回上一个月的 'YYYY-MM'（月报在每月 1 日生成上月数据）。"""
    today = today or datetime.now(UTC).date()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"
