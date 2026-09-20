"""质量统计业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import (
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


async def _fetch_feishu_records(
    db: AsyncSession, entity_code: str
) -> list[dict[str, Any]]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    return await feishu_sync_service.feishu_sync.search_records(db, entity_code, None)


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
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    records = await _fetch_feishu_records(db, "capa_ledger")
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = (
        runtime.get_entity_config("capa_ledger", direction="pull")
        if runtime.is_enabled()
        else None
    )

    total = len(records)
    closed_count = 0
    overdue_count = 0
    status_map: dict[str, int] = {}
    source_map: dict[str, int] = {}
    category_map: dict[str, int] = {}
    department_map: dict[str, int] = {}

    for record in records:
        fields = record.get("fields") or {}
        status = normalize_text(field_value(entity, fields, "状态")) or "未知"
        source = normalize_text(field_value(entity, fields, "来源")) or "未知"
        category = (
            normalize_text(field_value(entity, fields, "CAPA类型"))
            or normalize_text(field_value(entity, fields, "类型"))
            or "未知"
        )
        department = (
            normalize_text(field_value(entity, fields, "责任部门"))
            or normalize_text(field_value(entity, fields, "部门"))
            or "未知"
        )

        # 部门数据隔离：CAPA 按责任部门过滤
        if scope is not None and not scope.is_all and not scope.allows(department):
            continue

        status_map[status] = status_map.get(status, 0) + 1
        source_map[source] = source_map.get(source, 0) + 1
        category_map[category] = category_map.get(category, 0) + 1
        department_map[department] = department_map.get(department, 0) + 1

        if status in ("已关闭", "closed", "完成", "已完成"):
            closed_count += 1

    status_distribution = [{"status": k, "count": v} for k, v in status_map.items()]
    source_distribution = [{"source": k, "count": v} for k, v in source_map.items()]
    category_distribution = [
        {"category": k, "count": v} for k, v in category_map.items()
    ]
    department_distribution = [
        {"name": k, "count": v} for k, v in department_map.items()
    ]

    return CapaStatistics(
        total=total,
        closed_count=closed_count,
        overdue_count=overdue_count,
        status_distribution=status_distribution,
        source_distribution=source_distribution,
        category_distribution=category_distribution,
        department_distribution=department_distribution,
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
