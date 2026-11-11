"""安全承诺日报 AI 风险研判（应急〔2018〕74号 承诺公告制度）。

汇总当日作业情况（特殊作业报备 + 作业票）、未关闭隐患、危化品超储
（镜像口径优先，回退本地库存）与当日事故，调用平台统一 llm_client
生成辅助研判结果。

边界：AI 输出仅作辅助展示（risk_assessment JSONB），不替代权限判断、
数据库约束与人工确认；识别失败返回 (None, 人话原因)，不影响日报主流程。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import llm_client
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.models import (
    Accident,
    ChemicalInventory,
    HazardousChemical,
    HazardReport,
    SafetyCommitmentReport,
    SpecialOperationReport,
    WorkPermit,
)
from app.modules.safety.page_tables import HAZCHEM_PAGE_KEY
from app.modules.safety.schemas.safety_commitment import RISK_LEVELS
from app.modules.safety.service.dashboard import CN_TZ, shanghai_today_range
from app.modules.safety.service.hazchem import inventory_over_limit
from app.modules.safety.service.page_table import collect_mirror_over_limit_rows

logger = logging.getLogger(__name__)

_EXPECTED_KEYS = ["risk_level", "summary", "key_risks", "suggestions"]

# 数据采集上限：避免极端数据量撑爆 prompt
_MAX_ITEMS_IN_PROMPT = 20

_PROMPT_TEMPLATE = """你是化工企业的安全管理助手。
请根据以下当日安全数据，按照《危险化学品企业安全风险研判与承诺公告制度》
（应急〔2018〕74号）的要求，输出当日安全风险研判结果。

报告日期：{report_date}

## 当日企业状态（人工填报）
{enterprise_status}

## 当日特殊作业（报备+作业票）
- 特殊作业报备 {ops_report_total} 项：{ops_report_items}
- 作业票（approved/active）{permit_total} 张：{permit_items}

## 未关闭隐患
共 {hazard_total} 条{hazard_by_level}

## 危化品超储
{over_limit}

## 当日事故
{accidents}

## 输出要求
仅输出 JSON 对象，字段如下：
- risk_level：当日综合风险等级，只能是 {risk_levels} 之一
- summary：150 字以内的当日风险综合研判结论
- key_risks：主要风险点列表（每条一句话，最多 5 条；无则空数组）
- suggestions：管控建议列表（每条一句话，最多 5 条；无则空数组）
"""


def _short(text: str | None, limit: int = 60) -> str:
    normalized = (text or "").strip().replace("\n", " ")
    return normalized[:limit] + ("…" if len(normalized) > limit else "")


async def _collect_today_operations(
    db: AsyncSession, day_start: datetime, day_end: datetime
) -> tuple[int, list[str], int, list[str]]:
    """当日特殊作业：报备表 + 作业票（approved/active）。"""
    ops_rows = (
        await db.execute(
            select(SpecialOperationReport).where(
                SpecialOperationReport.is_deleted.is_(False),
                SpecialOperationReport.planned_start_time >= day_start,
                SpecialOperationReport.planned_start_time < day_end,
                SpecialOperationReport.status.notin_(["draft", "rejected"]),
            )
        )
    ).scalars()
    ops_items = [
        _short(f"{row.operation_type}·{row.location or ''}") for row in ops_rows
    ][:_MAX_ITEMS_IN_PROMPT]

    permit_rows = (
        await db.execute(
            select(WorkPermit).where(
                WorkPermit.is_deleted.is_(False),
                WorkPermit.status.in_(["approved", "active"]),
                or_(
                    WorkPermit.planned_start_time.is_(None),
                    WorkPermit.planned_start_time < day_end,
                ),
                or_(
                    WorkPermit.planned_end_time.is_(None),
                    WorkPermit.planned_end_time >= day_start,
                ),
            )
        )
    ).scalars()
    permit_items = [
        _short(f"{row.permit_no}·{row.permit_type}·{row.permit_level}")
        for row in permit_rows
    ][:_MAX_ITEMS_IN_PROMPT]
    return len(ops_items), ops_items, len(permit_items), permit_items


async def _collect_open_hazards(db: AsyncSession) -> tuple[int, str]:
    """未关闭隐患数量与等级分布。"""
    rows = (
        await db.execute(
            select(
                HazardReport.hazard_level, func.count(HazardReport.id)
            ).where(
                HazardReport.is_deleted.is_(False),
                or_(
                    HazardReport.status.is_(None),
                    HazardReport.status.notin_(["closed", "verified"]),
                ),
            ).group_by(HazardReport.hazard_level)
        )
    ).all()
    total = sum(int(count) for _, count in rows)
    parts = [
        f"{level or '未分级'} {int(count)} 条"
        for level, count in rows
        if level
    ]
    by_level = f"（{'，'.join(parts)}）" if parts else ""
    return total, by_level


async def _collect_over_limit_chemicals(db: AsyncSession) -> list[str]:
    """超储危化品清单（镜像口径优先，回退本地库存，同驾驶舱口径）。"""
    items: list[str] = []
    mirror_rows = await collect_mirror_over_limit_rows(db, HAZCHEM_PAGE_KEY)
    if mirror_rows is not None:
        for row in mirror_rows:
            if not row.over_limit:
                continue
            over_pct = f"（超 {row.over_pct:.0f}%）" if row.over_pct else ""
            items.append(
                f"{row.name or '（未识别品名）'}@{row.workshop}"
                f" {row.quantity}{over_pct}"
            )
    else:
        rows = (
            await db.execute(
                select(ChemicalInventory, HazardousChemical).join(
                    HazardousChemical,
                    ChemicalInventory.chemical_id == HazardousChemical.id,
                ).where(
                    ChemicalInventory.is_deleted.is_(False),
                    ChemicalInventory.upper_limit.isnot(None),
                )
            )
        ).all()
        for inventory, chemical in rows:
            if not inventory_over_limit(inventory.quantity, inventory.upper_limit):
                continue
            items.append(
                f"{chemical.name}@{inventory.workshop}"
                f" {inventory.quantity}/{inventory.upper_limit}{inventory.unit}"
            )
    return items[:_MAX_ITEMS_IN_PROMPT]


async def _collect_today_accidents(
    db: AsyncSession, day_start: datetime
) -> list[str]:
    rows = (
        await db.execute(
            select(Accident).where(
                Accident.is_deleted.is_(False),
                Accident.happened_at >= day_start,
            )
        )
    ).scalars()
    return [_short(row.description or row.accident_no) for row in rows][
        :_MAX_ITEMS_IN_PROMPT
    ]


async def collect_daily_context(
    db: AsyncSession, report_date: Any
) -> dict[str, Any]:
    """汇总当日研判数据依据（data_basis），供 prompt 与前端展示共用。"""
    day_start, day_end = shanghai_today_range()
    # 查历史日期时按报告日期推算当天区间（上海时区）
    today_str = day_start.astimezone(CN_TZ).date().isoformat()
    if report_date and str(report_date) != today_str:
        day_start = datetime.strptime(str(report_date), "%Y-%m-%d").replace(
            tzinfo=CN_TZ
        )
        day_end = day_start + timedelta(days=1)

    (
        ops_report_total,
        ops_report_items,
        permit_total,
        permit_items,
    ) = await _collect_today_operations(db, day_start, day_end)
    hazard_total, hazard_by_level = await _collect_open_hazards(db)
    over_limit_items = await _collect_over_limit_chemicals(db)
    accidents = await _collect_today_accidents(db, day_start)

    return {
        "report_date": str(report_date),
        "ops_report_total": ops_report_total,
        "ops_report_items": ops_report_items,
        "permit_total": permit_total,
        "permit_items": permit_items,
        "hazard_total": hazard_total,
        "hazard_by_level": hazard_by_level,
        "over_limit_items": over_limit_items,
        "accidents": accidents,
    }


def _build_prompt(context: dict[str, Any], enterprise_status: dict[str, Any]) -> str:
    over_limit = (
        "\n".join(f"- {item}" for item in context["over_limit_items"])
        if context["over_limit_items"]
        else "- 无超储项"
    )
    accidents = (
        "\n".join(f"- {item}" for item in context["accidents"])
        if context["accidents"]
        else "- 无"
    )
    return _PROMPT_TEMPLATE.format(
        report_date=context["report_date"],
        enterprise_status=json.dumps(enterprise_status, ensure_ascii=False),
        ops_report_total=context["ops_report_total"],
        ops_report_items=(
            "\n".join(f"- {item}" for item in context["ops_report_items"])
            or "- 无"
        ),
        permit_total=context["permit_total"],
        permit_items=(
            "\n".join(f"- {item}" for item in context["permit_items"]) or "- 无"
        ),
        hazard_total=context["hazard_total"],
        hazard_by_level=context["hazard_by_level"],
        over_limit=over_limit,
        accidents=accidents,
        risk_levels="/".join(RISK_LEVELS),
    )


def _validate_assessment(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并规整 AI 输出；不合法字段抛 ValueError。"""
    risk_level = str(raw.get("risk_level") or "").strip()
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"AI 输出风险等级无效：{risk_level!r}")
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        raise ValueError("AI 未输出研判结论")

    def _clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][
            :_MAX_ITEMS_IN_PROMPT
        ]

    return {
        "risk_level": risk_level,
        "summary": summary,
        "key_risks": _clean_list(raw.get("key_risks")),
        "suggestions": _clean_list(raw.get("suggestions")),
    }


async def generate_risk_assessment(
    db: AsyncSession, report: SafetyCommitmentReport
) -> tuple[SafetyCommitmentReport | None, str | None]:
    """为日报生成 AI 风险研判，返回（已更新日报, 失败原因）。

    识别失败只返回原因，不影响日报主流程。
    """
    context = await collect_daily_context(db, report.report_date)
    prompt = _build_prompt(context, report.enterprise_status or {})
    try:
        raw = await llm_client.chat_json(
            [{"role": "user", "content": prompt}],
            expected_keys=_EXPECTED_KEYS,
        )
    except LLMConfigError:
        return None, "平台未配置 AI 模型，无法自动研判"
    except LLMRateLimitError:
        return None, "AI 模型限流，请稍后重试研判"
    except LLMOutputError:
        return None, "AI 研判结果格式无效，请重试"
    except LLMProviderError:
        return None, "AI 模型服务暂不可用，请稍后重试研判"
    except ValueError as exc:
        return None, str(exc)

    try:
        assessment = _validate_assessment(raw)
    except ValueError as exc:
        return None, str(exc)

    report.risk_assessment = {
        **assessment,
        "data_basis": {
            "ops_report_total": context["ops_report_total"],
            "permit_total": context["permit_total"],
            "hazard_total": context["hazard_total"],
            "over_limit_total": len(context["over_limit_items"]),
            "accident_total": len(context["accidents"]),
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "edited": False,
    }
    await db.flush()
    logger.info(
        "安全承诺日报 AI 研判完成: date=%s risk_level=%s",
        report.report_date,
        assessment["risk_level"],
    )
    return report, None
