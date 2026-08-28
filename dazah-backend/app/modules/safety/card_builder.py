"""Scheduled task card builder — template rendering and data aggregation."""

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ── Available Data Sources ──
# Each entry defines a data key that can be selected in the UI.
# The `fetcher` is a callable(repo) -> str | int that returns the aggregated value.

DATA_SOURCE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "hazard_open_count",
        "label": "未关闭隐患数",
        "description": "当前状态为「未关闭」(status=open) 的隐患数量",
        "default_enabled": True,
    },
    {
        "key": "hazard_open_details",
        "label": "未关闭隐患明细",
        "description": (
            "所有未关闭隐患的详细列表（编号、位置、等级、描述、责任部门、发现日期、"
            "整改状态、限期）"
        ),
        "default_enabled": True,
    },
    {
        "key": "hazard_total_count",
        "label": "隐患总数",
        "description": "系统中所有未删除的隐患总数",
        "default_enabled": False,
    },
    {
        "key": "check_today_count",
        "label": "今日检查数",
        "description": "今日创建的安全检查数量",
        "default_enabled": True,
    },
    {
        "key": "check_week_count",
        "label": "本周检查数",
        "description": "本周创建的安全检查数量",
        "default_enabled": False,
    },
    {
        "key": "accident_month_count",
        "label": "本月事故数",
        "description": "本月登记的事故数量",
        "default_enabled": True,
    },
    {
        "key": "accident_year_count",
        "label": "本年事故数",
        "description": "本年登记的事故数量",
        "default_enabled": False,
    },
    {
        "key": "training_due_count",
        "label": "待培训人数",
        "description": "培训计划中状态为「待培训」的人数",
        "default_enabled": False,
    },
    {
        "key": "training_month_count",
        "label": "本月培训数",
        "description": "本月完成的培训数量",
        "default_enabled": False,
    },
    {
        "key": "ehs_change_pending_count",
        "label": "待审批变更数",
        "description": "EHS 变更中状态为「待审批」的数量",
        "default_enabled": False,
    },
    {
        "key": "special_ops_active_count",
        "label": "进行中特殊作业数",
        "description": "当前进行中的特殊作业数量",
        "default_enabled": False,
    },
    {
        "key": "contractor_active_count",
        "label": "在场承包商数",
        "description": "当前在场的承包商数量",
        "default_enabled": False,
    },
    {
        "key": "oh_exam_due_count",
        "label": "待体检人数",
        "description": "职业健康体检到期或即将到期人数",
        "default_enabled": False,
    },
]


async def fetch_data_sources(repo: Any, enabled_keys: list[str]) -> dict[str, str]:
    """Fetch all enabled data sources and return a dict of {key: formatted_value}."""
    from datetime import timedelta

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    fetchers: dict[str, Callable[[], Awaitable[Any]]] = {
        "hazard_open_count": lambda: _count_pending_hazards(repo),
        "hazard_open_details": lambda: _fetch_open_hazards_details(repo),
        "hazard_total_count": lambda: _count_total_hazards(repo),
        "check_today_count": lambda: _count_checks_since(repo, today),
        "check_week_count": lambda: _count_checks_since(repo, week_start),
        "accident_month_count": lambda: _count_accidents_since(repo, month_start),
        "accident_year_count": lambda: _count_accidents_since(repo, year_start),
        "training_due_count": lambda: _count_due_trainings(repo),
        "training_month_count": lambda: _count_trainings_since(repo, month_start),
        "ehs_change_pending_count": lambda: _count_pending_ehs_changes(repo),
        "special_ops_active_count": lambda: _count_active_special_ops(repo),
        "contractor_active_count": lambda: _count_active_contractors(repo),
        "oh_exam_due_count": lambda: _count_due_oh_exams(repo),
    }

    results: dict[str, str] = {}
    for key in enabled_keys:
        fetcher = fetchers.get(key)
        if fetcher:
            try:
                value = await fetcher()
                results[key] = str(value)
            except Exception as e:
                logger.error("Error fetching data source %s: %s", key, e)
                results[key] = "—"
        else:
            results[key] = "—"
    return results


def get_data_source_label(key: str) -> str:
    """Get the display label for a data source key."""
    for ds in DATA_SOURCE_DEFINITIONS:
        if ds["key"] == key:
            return str(ds["label"])
    return key


def build_default_template(enabled_sources: list[dict[str, Any]]) -> str:
    """Auto-generate a default card template from enabled data sources."""
    lines = ["**📊 安全数据简报**", ""]
    for src in enabled_sources:
        if src.get("enabled", True):
            lines.append(f"- **{src['label']}**: {{{{ {src['key']} }}}}")
    lines.append("")
    lines.append("---")
    lines.append("⏰ 数据截止: {{ runtime.timestamp }}")
    return "\n".join(lines)


def render_template(template: str, variables: dict[str, str]) -> str:
    """Replace {{ key }} placeholders with actual values."""

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return variables.get(key, f"{{{{{key}}}}}")

    return re.sub(r"\{\{\s*([^}]+)\s*\}\}", replacer, template)


async def build_card_json(
    title: str,
    rendered_markdown: str,
    header_color: str = "blue",
) -> str:
    """Build a Feishu interactive card JSON string.

    Delegates to the safety feishu notification module's build_card.
    """
    from app.modules.safety.feishu.notification import build_card

    result = await build_card(
        title=title, content=rendered_markdown, header_template=header_color
    )
    if not isinstance(result, str):
        raise TypeError("飞书卡片构建结果不是字符串")
    return result


# ── Internal fetcher helpers ──


async def _count_pending_hazards(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import HazardReport

    query = (
        select(func.count())
        .select_from(HazardReport)
        .where(
            HazardReport.is_deleted.is_(False),
            HazardReport.status == "open",
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _fetch_open_hazards_details(repo: Any) -> str:
    """Query all open hazards and return a markdown-formatted detail list."""
    from sqlalchemy import select

    from app.modules.safety.models import HazardReport

    query = (
        select(HazardReport)
        .where(
            HazardReport.is_deleted.is_(False),
            HazardReport.status == "open",
        )
        .order_by(HazardReport.hazard_level.desc(), HazardReport.discovered_at.desc())
    )
    result = await repo.session.execute(query)
    hazards = result.scalars().all()

    if not hazards:
        return "✅ 当前无未关闭隐患"

    level_map = {"general": "一般", "major": "较大", "critical": "重大"}
    status_map = {
        "pending": "待整改",
        "in_progress": "整改中",
        "replied": "已回复",
        "completed": "已完成",
    }

    lines: list[str] = []
    for i, h in enumerate(hazards, 1):
        icon = (
            "⚠️"
            if h.hazard_level == "critical"
            else "🔶"
            if h.hazard_level == "major"
            else "🔹"
        )
        level = level_map.get(h.hazard_level, h.hazard_level or "—")
        desc = h.description or "—"
        # 截断过长的描述
        if len(desc) > 60:
            desc = desc[:57] + "..."
        dept = h.department or "—"
        discovered = h.discovered_at.strftime("%Y-%m-%d") if h.discovered_at else "—"
        deadline = h.deadline.strftime("%Y-%m-%d") if h.deadline else "—"
        status = status_map.get(h.rectification_status, h.rectification_status or "—")

        lines.append(
            f"**{i}. {h.hazard_no}** | "
            f"{icon} {level}\n"
            f"描述：{desc}\n"
            f"责任：{dept} | 发现：{discovered} | 限期：{deadline} | {status}\n"
        )

    return "\n".join(lines)


async def _count_total_hazards(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import HazardReport

    query = (
        select(func.count())
        .select_from(HazardReport)
        .where(HazardReport.is_deleted.is_(False))
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_checks_since(repo: Any, since_date: date) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import SafetyCheck

    query = (
        select(func.count())
        .select_from(SafetyCheck)
        .where(
            SafetyCheck.is_deleted.is_(False),
            SafetyCheck.created_at >= since_date,
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_accidents_since(repo: Any, since_date: date) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import Accident

    query = (
        select(func.count())
        .select_from(Accident)
        .where(
            Accident.is_deleted.is_(False),
            Accident.created_at >= since_date,
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_due_trainings(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import SafetyTraining

    query = (
        select(func.count())
        .select_from(SafetyTraining)
        .where(
            SafetyTraining.is_deleted.is_(False),
            SafetyTraining.status == "pending",
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_trainings_since(repo: Any, since_date: date) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import SafetyTraining

    query = (
        select(func.count())
        .select_from(SafetyTraining)
        .where(
            SafetyTraining.is_deleted.is_(False),
            SafetyTraining.created_at >= since_date,
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_pending_ehs_changes(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import EhsChange

    query = (
        select(func.count())
        .select_from(EhsChange)
        .where(
            EhsChange.is_deleted.is_(False),
            EhsChange.status == "pending_approval",
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_active_special_ops(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import SpecialOperationPermit

    query = (
        select(func.count())
        .select_from(SpecialOperationPermit)
        .where(
            SpecialOperationPermit.is_deleted.is_(False),
            SpecialOperationPermit.status.in_(["pending", "in_progress"]),
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_active_contractors(repo: Any) -> int:
    from sqlalchemy import func, select

    from app.modules.safety.models import Contractor

    query = (
        select(func.count())
        .select_from(Contractor)
        .where(
            Contractor.is_deleted.is_(False),
            Contractor.status == "active",
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0


async def _count_due_oh_exams(repo: Any) -> int:
    from datetime import date

    from sqlalchemy import func, select

    from app.modules.safety.models import OhHealthExam

    query = (
        select(func.count())
        .select_from(OhHealthExam)
        .where(
            OhHealthExam.is_deleted.is_(False),
            OhHealthExam.scheduled_date <= date.today(),
        )
    )
    result = await repo.session.execute(query)
    return result.scalar() or 0
