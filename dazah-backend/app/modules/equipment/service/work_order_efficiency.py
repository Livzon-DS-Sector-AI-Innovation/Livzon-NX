"""维修效能统计：聚合 SQL 数据源与只读聚合服务。

口径（全部来自 equipment.work_orders 已有时间戳，无新表）：
- 平均响应时长：assigned_at − reported_at（报修→接单），分钟
- MTTR：actual_duration（提交完成时记录），分钟
- 紧急 5 分钟达标率：priority=紧急 且响应 ≤5min 的占比
- 月度趋势：reported_at 按年月分组
- 故障 TOP10：按设备聚合工单数与平均修复时长
- 维修人员排行：按接单人聚合，姓名经二次查询（不跨模块 join identity 表）
- 响应时效分布：≤5/5-30/30-120/>120 分钟四档 + 未接单，五档之和=区间内全部工单
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.work_order import WorkOrder

_BUCKET_ORDER = ["≤5分钟", "5-30分钟", "30-120分钟", ">120分钟", "未接单"]


def _months_back(months: int) -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC) - timedelta(
        days=31 * max(months, 1)
    )


def _base_filters(workshop_code: str | None, since: datetime):
    filters = [
        WorkOrder.is_deleted == False,  # noqa: E712
        WorkOrder.reported_at >= since,
    ]
    if workshop_code:
        filters.append(Equipment.workshop_code == workshop_code)
    return filters


async def get_efficiency_statistics(
    db: AsyncSession, workshop_code: str | None = None, months: int = 6
) -> dict[str, object]:
    """聚合维修效能指标；workshop_code 为空 = 全车间。"""
    since = _months_back(months)
    filters = _base_filters(workshop_code, since)

    join = WorkOrder.__table__.join(
        Equipment.__table__, WorkOrder.equipment_id == Equipment.id
    )

    # 总体指标：平均响应 / MTTR / 紧急达标
    response_expr = func.avg(
        func.extract(
            "epoch", WorkOrder.assigned_at - WorkOrder.reported_at
        )
        / 60.0
    )
    overall = (
        await db.execute(
            select(
                response_expr.label("avg_response"),
                func.avg(WorkOrder.actual_duration).label("avg_repair"),
                func.count().label("total"),
            )
            .select_from(join)
            .where(
                *filters,
                WorkOrder.assigned_at.isnot(None),
            )
        )
    ).first()
    urgent = (
        await db.execute(
            select(
                func.count().label("urgent_total"),
                func.sum(
                    case(
                        (
                            func.extract(
                                "epoch",
                                WorkOrder.assigned_at - WorkOrder.reported_at,
                            )
                            <= 300.0,
                            1,
                        ),
                        else_=0,
                    )
                ).label("urgent_on_time"),
            )
            .select_from(join)
            .where(*filters, WorkOrder.priority == "紧急")
        )
    ).first()

    # 月度趋势
    month_expr = func.to_char(
        func.date_trunc("month", WorkOrder.reported_at), "YYYY-MM"
    )
    trend_rows = (
        (
            await db.execute(
                select(
                    month_expr.label("month"),
                    func.count().label("total"),
                    func.sum(
                        case(
                            (WorkOrder.status.in_(["已完成", "已关闭"]), 1),
                            else_=0,
                        )
                    ).label("completed"),
                    func.sum(
                        case((WorkOrder.priority == "紧急", 1), else_=0)
                    ).label("urgent"),
                    response_expr.label("avg_response"),
                    func.avg(WorkOrder.actual_duration).label("avg_repair"),
                )
                .select_from(join)
                .where(*filters)
                .group_by(month_expr)
                .order_by(month_expr)
            )
        )
        .all()
    )

    # 故障 TOP10
    top_rows = (
        (
            await db.execute(
                select(
                    Equipment.id.label("equipment_id"),
                    Equipment.name.label("equipment_name"),
                    Equipment.equipment_no.label("equipment_no"),
                    Equipment.workshop_code.label("workshop_code"),
                    func.count().label("order_count"),
                    func.avg(WorkOrder.actual_duration).label(
                        "avg_repair_minutes"
                    ),
                )
                .select_from(join)
                .where(*filters)
                .group_by(
                    Equipment.id,
                    Equipment.name,
                    Equipment.equipment_no,
                    Equipment.workshop_code,
                )
                .order_by(func.count().desc())
                .limit(10)
            )
        )
        .all()
    )

    # 维修人员排行：接单人聚合前 5（姓名二次查询，避免跨模块 join）
    rank_rows = (
        (
            await db.execute(
                select(
                    WorkOrder.assignee_id.label("assignee_id"),
                    func.count().label("order_count"),
                    response_expr.label("avg_response"),
                    func.avg(WorkOrder.actual_duration).label("avg_repair"),
                )
                .select_from(join)
                .where(*filters, WorkOrder.assignee_id.isnot(None))
                .group_by(WorkOrder.assignee_id)
                .order_by(func.count().desc())
                .limit(5)
            )
        )
        .all()
    )
    assignee_names: dict[object, str] = {}
    if rank_rows:
        from app.platform.identity.models import User

        user_rows = (
            (
                await db.execute(
                    select(User.id, User.name).where(
                        User.id.in_([r.assignee_id for r in rank_rows])
                    )
                )
            )
            .all()
        )
        assignee_names = {u.id: u.name for u in user_rows}

    # 响应时效分布：五档（NULL 判断必须放最前，否则未接单落进 >120 档）
    resp_minutes = (
        func.extract("epoch", WorkOrder.assigned_at - WorkOrder.reported_at)
        / 60.0
    )
    bucket_expr = case(
        (WorkOrder.assigned_at.is_(None), "未接单"),
        (resp_minutes <= 5, "≤5分钟"),
        (resp_minutes <= 30, "5-30分钟"),
        (resp_minutes <= 120, "30-120分钟"),
        else_=">120分钟",
    )
    bucket_rows = (
        (
            await db.execute(
                select(bucket_expr.label("bucket"), func.count().label("cnt"))
                .select_from(join)
                .where(*filters)
                .group_by(bucket_expr)
            )
        )
        .all()
    )
    bucket_counts = {row.bucket: int(row.cnt) for row in bucket_rows}
    bucket_total = sum(bucket_counts.values())

    avg_response = float(overall.avg_response or 0) if overall else 0.0
    avg_repair = float(overall.avg_repair or 0) if overall else 0.0
    urgent_total = int(urgent.urgent_total or 0) if urgent else 0
    urgent_on_time = int(urgent.urgent_on_time or 0) if urgent else 0

    return {
        "avg_response_minutes": round(avg_response, 1),
        "avg_repair_minutes": round(avg_repair, 1),
        "urgent_total": urgent_total,
        "urgent_on_time": urgent_on_time,
        "urgent_5min_rate": (
            round(urgent_on_time / urgent_total, 3) if urgent_total else None
        ),
        "total_orders": int(overall.total or 0) if overall else 0,
        "monthly": [
            {
                "month": row.month,
                "total": int(row.total),
                "completed": int(row.completed or 0),
                "urgent": int(row.urgent or 0),
                "avg_response": round(float(row.avg_response or 0), 1),
                "avg_repair": round(float(row.avg_repair or 0), 1),
            }
            for row in trend_rows
        ],
        "top_faults": [
            {
                "equipment_id": str(row.equipment_id),
                "equipment_name": row.equipment_name or "",
                "equipment_no": row.equipment_no or "",
                "workshop_code": row.workshop_code or "",
                "order_count": int(row.order_count),
                "avg_repair_minutes": round(float(row.avg_repair_minutes or 0), 1),
            }
            for row in top_rows
        ],
        "repairer_ranking": [
            {
                "assignee_id": str(row.assignee_id),
                "assignee_name": assignee_names.get(row.assignee_id) or "未知",
                "order_count": int(row.order_count),
                "avg_response_minutes": round(float(row.avg_response or 0), 1),
                "avg_repair_minutes": round(float(row.avg_repair or 0), 1),
            }
            for row in rank_rows
        ],
        "response_buckets": [
            {
                "bucket": bucket,
                "count": bucket_counts.get(bucket, 0),
                "ratio": (
                    round(bucket_counts.get(bucket, 0) / bucket_total, 3)
                    if bucket_total
                    else 0.0
                ),
            }
            for bucket in _BUCKET_ORDER
        ],
    }


__all__: list[str] = ["get_efficiency_statistics"]
