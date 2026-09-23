"""质量统计业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import (
    CAPA,
    ChangeActionPlan,
    ChangeControl,
    Deviation,
)
from app.modules.quality.schemas import (
    CapaStatistics,
    ChangeStatistics,
    DeviationStatistics,
)
from app.platform.identity.data_scope import DepartmentScope, department_in_clause

logger = logging.getLogger(__name__)


async def get_deviation_statistics(
    db: AsyncSession,
    scope: DepartmentScope | None = None,
) -> DeviationStatistics:
    from app.modules.quality.service import deviation_cause_analysis

    # 部门数据隔离（后台可配置可见部门范围），本地 department 列直接过滤
    scope_clause = department_in_clause(Deviation.department, scope) if scope else None
    scope_where = [scope_clause] if scope_clause is not None else []

    # 偏差台账已本地化：以 quality.deviations 表为唯一数据源统计，不再依赖飞书
    result = await db.execute(
        select(Deviation).where(
            Deviation.is_deleted.is_(False),
            *scope_where,
        )
    )
    records = list(result.scalars().all())

    # 懒加载补齐根因归类（AI 优先、关键词兜底），已有人工填写值不覆盖
    await deviation_cause_analysis.fill_missing_analysis(db, records)

    total = len(records)
    closed_count = 0
    major_count = 0
    dept_map: dict[str, int] = {}
    level_map: dict[str, int] = {}
    cause_map: dict[str, int] = {}
    monthly_counter: dict[str, int] = {}

    for record in records:
        if record.status == "closed":
            closed_count += 1
        if record.level == "major":
            major_count += 1

        # 部门：本地 department 列（SQL 层已按 scope 过滤）
        dept = (record.department or "").strip() or "未知"
        dept_map[dept] = dept_map.get(dept, 0) + 1

        # 等级：本地 level 枚举（minor/moderate/major），输出原文，前端映射中文展示
        level = (record.level or "").strip() or "未定级"
        level_map[level] = level_map.get(level, 0) + 1

        # 根本原因归类：人机料法环口径，与 CAPA 原因类别一致
        category = (record.root_cause_category or "").strip() or "其它"
        cause_map[category] = cause_map.get(category, 0) + 1

        # 月度趋势：发现日期优先，回退调查完成时间/创建时间
        occurred_at = (
            record.discovery_date
            or record.investigation_completed_at
            or record.created_at
        )
        if occurred_at is not None:
            month_key = occurred_at.strftime("%Y-%m")
            monthly_counter[month_key] = monthly_counter.get(month_key, 0) + 1

    department_distribution = sorted(
        ({"name": k, "count": v} for k, v in dept_map.items()),
        key=lambda row: row["count"],
        reverse=True,
    )
    level_order = {"minor": 0, "moderate": 1, "major": 2, "未定级": 3}
    level_distribution = sorted(
        ({"name": k, "count": v} for k, v in level_map.items()),
        key=lambda row: (level_order.get(row["name"], len(level_order)), -row["count"]),
    )
    cause_order = {
        name: index
        for index, name in enumerate(deviation_cause_analysis.REASON_CATEGORIES)
    }
    root_cause_distribution = sorted(
        ({"name": k, "count": v} for k, v in cause_map.items()),
        key=lambda row: (cause_order.get(row["name"], len(cause_order)), -row["count"]),
    )

    now = datetime.now(UTC)
    monthly_trend: list[dict[str, Any]] = []
    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_key = f"{year:04d}-{month:02d}"
        monthly_trend.append(
            {"month": month_key, "count": monthly_counter.get(month_key, 0)}
        )

    return DeviationStatistics(
        total=total,
        closed_count=closed_count,
        major_count=major_count,
        level_distribution=level_distribution,
        department_distribution=department_distribution,
        root_cause_distribution=root_cause_distribution,
        monthly_trend=monthly_trend,
    )


async def get_capa_statistics(
    db: AsyncSession,
    scope: DepartmentScope | None = None,
) -> CapaStatistics:
    """CAPA 台账统计。

    CAPA 台账已本地化：以 quality.capas 表为唯一数据源，按台账列口径统计
    （效果评估、事件部门、启动日期趋势），空值归入「未填」。
    """
    # 部门数据隔离（后台可配置可见部门范围），本地 department 列直接过滤
    scope_clause = department_in_clause(CAPA.department, scope) if scope else None
    scope_where = [scope_clause] if scope_clause is not None else []

    result = await db.execute(
        select(CAPA).where(
            CAPA.is_deleted.is_(False),
            *scope_where,
        )
    )
    records = list(result.scalars().all())

    total = len(records)
    closed_count = 0
    result_map: dict[str, int] = {}
    department_map: dict[str, int] = {}
    monthly_counter: dict[str, int] = {}

    for record in records:
        if record.closure_date is not None:
            closed_count += 1

        # CAPA效果评估：台账列原文（有效/无效/进行中），空值记「未填」
        evaluation = (record.evaluation_result or "").strip() or "未填"
        result_map[evaluation] = result_map.get(evaluation, 0) + 1

        # 事件部门：台账列原文，空值记「未填」
        department = (record.department or "").strip() or "未填"
        department_map[department] = department_map.get(department, 0) + 1

        # 月度趋势：启动日期优先（本地存于 expected_completion_date），回退创建时间
        started_at = record.expected_completion_date or record.created_at
        if started_at is not None:
            month_key = started_at.strftime("%Y-%m")
            monthly_counter[month_key] = monthly_counter.get(month_key, 0) + 1

    result_order = {"有效": 0, "无效": 1, "进行中": 2, "未填": 3}
    result_distribution = sorted(
        ({"name": key, "count": value} for key, value in result_map.items()),
        key=lambda row: (
            result_order.get(row["name"], len(result_order)),
            -row["count"],
        ),
    )
    department_distribution = sorted(
        ({"name": key, "count": value} for key, value in department_map.items()),
        key=lambda row: row["count"],
        reverse=True,
    )

    now = datetime.now(UTC)
    monthly_trend: list[dict[str, Any]] = []
    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_key = f"{year:04d}-{month:02d}"
        monthly_trend.append(
            {"month": month_key, "count": monthly_counter.get(month_key, 0)}
        )

    return CapaStatistics(
        total=total,
        closed_count=closed_count,
        in_progress_count=total - closed_count,
        result_distribution=result_distribution,
        department_distribution=department_distribution,
        monthly_trend=monthly_trend,
    )


async def get_change_statistics(
    db: AsyncSession,
    scope: DepartmentScope | None = None,
    change_type: str = "technical",
) -> ChangeStatistics:
    # 部门数据隔离（后台可配置可见部门范围）
    scope_clause = (
        department_in_clause(ChangeControl.applicant_department, scope)
        if scope
        else None
    )
    scope_where = [scope_clause] if scope_clause is not None else []
    total_result = await db.execute(
        select(func.count())
        .select_from(ChangeControl)
        .where(
            ChangeControl.is_deleted.is_(False),
            ChangeControl.change_type == change_type,
            *scope_where,
        )
    )
    total = total_result.scalar_one()

    level_result = await db.execute(
        select(ChangeControl.change_level, func.count())
        .where(
            ChangeControl.is_deleted.is_(False),
            ChangeControl.change_type == change_type,
            *scope_where,
        )
        .group_by(ChangeControl.change_level)
    )
    level_distribution = [
        {"level": row[0] or "unknown", "count": row[1]} for row in level_result.all()
    ]

    rows = await db.execute(
        select(
            ChangeControl.closure_date,
            ChangeControl.execution_date,
            ChangeControl.planned_approval_date,
        ).where(
            ChangeControl.is_deleted.is_(False),
            ChangeControl.change_type == change_type,
            *scope_where,
        )
    )
    status_counter: dict[str, int] = {
        "draft": 0,
        "pending_approval": 0,
        "in_execution": 0,
        "closed": 0,
    }
    closed_count = 0
    delay_count = 0
    today = date.today()
    for closure_date, execution_date, planned_approval_date in rows.all():
        if closure_date:
            status_counter["closed"] += 1
            closed_count += 1
        elif execution_date:
            status_counter["in_execution"] += 1
        elif planned_approval_date:
            status_counter["pending_approval"] += 1
            if planned_approval_date < today:
                delay_count += 1
        else:
            status_counter["draft"] += 1

    status_distribution = [
        {"status": status, "count": count}
        for status, count in status_counter.items()
        if count > 0
    ]

    # 部门分布
    dept_result = await db.execute(
        select(ChangeControl.applicant_department, func.count())
        .where(
            ChangeControl.is_deleted.is_(False),
            ChangeControl.change_type == change_type,
            *scope_where,
        )
        .group_by(ChangeControl.applicant_department)
    )
    department_distribution = [
        {"name": row[0] or "未知", "count": row[1]} for row in dept_result.all()
    ]

    # 变更类型分布（按变更对象分组）
    type_result = await db.execute(
        select(ChangeControl.change_object, func.count())
        .where(
            ChangeControl.is_deleted.is_(False),
            ChangeControl.change_type == change_type,
            *scope_where,
        )
        .group_by(ChangeControl.change_object)
    )
    type_distribution = [
        {"name": row[0] or "未知", "count": row[1]} for row in type_result.all()
    ]

    action_plan_total_result = await db.execute(
        select(func.count())
        .select_from(ChangeActionPlan)
        .where(ChangeActionPlan.is_deleted.is_(False))
    )
    action_plan_total = action_plan_total_result.scalar_one()

    action_plan_overdue_result = await db.execute(
        select(func.count())
        .select_from(ChangeActionPlan)
        .where(
            ChangeActionPlan.is_deleted.is_(False),
            func.coalesce(
                ChangeActionPlan.delayed_deadline_date, ChangeActionPlan.deadline_date
            )
            < today,
            ChangeActionPlan.reminder_confirmed_at.is_(None),
        )
    )
    action_plan_overdue = action_plan_overdue_result.scalar_one()

    action_plan_confirmed_result = await db.execute(
        select(func.count())
        .select_from(ChangeActionPlan)
        .where(
            ChangeActionPlan.is_deleted.is_(False),
            ChangeActionPlan.reminder_confirmed_at.is_not(None),
        )
    )
    action_plan_confirmed = action_plan_confirmed_result.scalar_one()

    return ChangeStatistics(
        total=total,
        closed_count=closed_count,
        delay_count=delay_count,
        status_distribution=status_distribution,
        level_distribution=level_distribution,
        type_distribution=type_distribution,
        department_distribution=department_distribution,
        action_plan_total=action_plan_total,
        action_plan_overdue=action_plan_overdue,
        action_plan_confirmed=action_plan_confirmed,
    )
