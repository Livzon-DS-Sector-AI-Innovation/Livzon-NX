"""设备健康度评分、每日快照与预警。

设计约束：
- 评分为纯函数（compute_health_score），权重可经 maintenance_config
  （config_key=health_score_weights）调整，默认内置；
- 快照任务每日一次，预警（评分跳变、重复故障）在快照后同批处理；
- LLM 不参与评分与预警判定，全部基于 SQL 聚合事实。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.calibration import CalibrationPlan
from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.health import (
    EquipmentHealthSnapshot,
    RepairProfile,
)
from app.modules.equipment.models.maintenance_plan import MaintenancePlan
from app.modules.equipment.models.work_order import WorkOrder

if TYPE_CHECKING:
    from app.modules.equipment.schemas import WorkOrderCreate

logger = logging.getLogger(__name__)

# 分档阈值
GRADE_GREEN_THRESHOLD = 85.0
GRADE_YELLOW_THRESHOLD = 60.0

# 默认权重（可被 maintenance_config.health_score_weights 覆盖）
DEFAULT_WEIGHTS: dict[str, float] = {
    "fault": 0.35,
    "mttr": 0.20,
    "maintenance": 0.25,
    "calibration": 0.10,
    "repeat": 0.10,
}

# 观察窗口（天）
_FAULT_WINDOW_DAYS = 90


@dataclass(frozen=True, slots=True)
class HealthMetrics:
    """单台设备健康度分项指标（SQL 聚合结果）"""

    fault_count_90d: int = 0
    mttr_min_90d: float | None = None
    overdue_maintenance_count: int = 0
    overdue_calibration_count: int = 0
    max_repeat_fault_90d: int = 0
    penalties: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealthScore:
    """评分结果"""

    score: float
    grade: str
    metrics: HealthMetrics


def _fault_penalty(count: int) -> float:
    """故障频率罚分：1 次 20 分，5 次及以上 100 分。"""
    return min(100.0, count * 20.0)


def _mttr_penalty(mttr_min: float | None) -> float:
    """平均修复时长罚分（分钟）：无数据不计罚分。"""
    if mttr_min is None:
        return 0.0
    if mttr_min <= 60:
        return 0.0
    if mttr_min <= 240:
        return 30.0
    if mttr_min <= 480:
        return 60.0
    return 100.0


def _overdue_penalty(count: int) -> float:
    """超期计划罚分：1 项 50 分，2 项及以上 100 分。"""
    return min(100.0, count * 50.0)


def _repeat_penalty(max_repeat: int) -> float:
    """90 天内同症状重复故障罚分：3 次 25 分，每多 1 次加 25，封顶 100。"""
    if max_repeat < 3:
        return 0.0
    return min(100.0, (max_repeat - 2) * 25.0)


def compute_health_score(
    metrics: HealthMetrics,
    weights: dict[str, float] | None = None,
) -> HealthScore:
    """按分项罚分加权计算健康度评分（0-100）并分档 G/Y/R。"""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: v for k, v in weights.items() if k in w})

    penalties = {
        "fault": _fault_penalty(metrics.fault_count_90d),
        "mttr": _mttr_penalty(metrics.mttr_min_90d),
        "maintenance": _overdue_penalty(metrics.overdue_maintenance_count),
        "calibration": _overdue_penalty(metrics.overdue_calibration_count),
        "repeat": _repeat_penalty(metrics.max_repeat_fault_90d),
    }
    total_penalty = sum(penalties[k] * w.get(k, 0.0) for k in penalties)
    score = max(0.0, min(100.0, 100.0 - total_penalty))
    if score >= GRADE_GREEN_THRESHOLD:
        grade = "G"
    elif score >= GRADE_YELLOW_THRESHOLD:
        grade = "Y"
    else:
        grade = "R"
    return HealthScore(
        score=round(score, 2),
        grade=grade,
        metrics=HealthMetrics(
            fault_count_90d=metrics.fault_count_90d,
            mttr_min_90d=metrics.mttr_min_90d,
            overdue_maintenance_count=metrics.overdue_maintenance_count,
            overdue_calibration_count=metrics.overdue_calibration_count,
            max_repeat_fault_90d=metrics.max_repeat_fault_90d,
            penalties=penalties,
        ),
    )


async def get_score_weights(db: AsyncSession) -> dict[str, float]:
    """读取可调权重（maintenance_config.health_score_weights，JSON 文本）。"""
    from app.modules.equipment.models.maintenance_config import MaintenanceConfig

    row = (
        await db.execute(
            select(MaintenanceConfig).where(
                MaintenanceConfig.config_key == "health_score_weights",
                MaintenanceConfig.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if not row:
        return dict(DEFAULT_WEIGHTS)
    import json

    try:
        data = json.loads(row.config_value)
    except (ValueError, TypeError):
        return dict(DEFAULT_WEIGHTS)
    if not isinstance(data, dict):
        return dict(DEFAULT_WEIGHTS)
    return {
        k: float(v)
        for k, v in data.items()
        if k in DEFAULT_WEIGHTS and isinstance(v, int | float)
    }


async def collect_metrics(
    db: AsyncSession, equipment_id: uuid.UUID, today: date | None = None
) -> HealthMetrics:
    """聚合单台设备的健康度分项指标。"""
    now = datetime.now(UTC)
    today = today or now.date()
    window_start = now - timedelta(days=_FAULT_WINDOW_DAYS)

    # 90 天故障工单（故障维修，未删除）
    fault_orders = (
        (
            await db.execute(
                select(WorkOrder).where(
                    WorkOrder.equipment_id == equipment_id,
                    WorkOrder.order_type == "故障维修",
                    WorkOrder.is_deleted == False,  # noqa: E712
                    WorkOrder.reported_at >= window_start,
                )
            )
        )
        .scalars()
        .all()
    )
    fault_count = len(fault_orders)
    durations = [
        o.actual_duration
        for o in fault_orders
        if o.actual_duration is not None and o.actual_duration > 0
    ]
    mttr = round(sum(durations) / len(durations), 1) if durations else None

    # 同症状重复故障（90 天）
    symptom_counts: dict[uuid.UUID, int] = {}
    for o in fault_orders:
        if o.fault_symptom_id is not None:
            symptom_counts[o.fault_symptom_id] = (
                symptom_counts.get(o.fault_symptom_id, 0) + 1
            )
    max_repeat = max(symptom_counts.values(), default=0)

    # 超期保养计划（启用中且下次维护日期已过）
    overdue_maintenance = (
        await db.execute(
            select(func.count())
            .select_from(MaintenancePlan)
            .where(
                MaintenancePlan.equipment_id == equipment_id,
                MaintenancePlan.status == "启用",
                MaintenancePlan.is_deleted == False,  # noqa: E712
                MaintenancePlan.next_maintenance_date < today,
            )
        )
    ).scalar_one()

    # 超期校准计划
    overdue_calibration = (
        await db.execute(
            select(func.count())
            .select_from(CalibrationPlan)
            .where(
                CalibrationPlan.equipment_id == equipment_id,
                CalibrationPlan.status == "启用",
                CalibrationPlan.is_deleted == False,  # noqa: E712
                CalibrationPlan.next_calibration_date < today,
            )
        )
    ).scalar_one()

    return HealthMetrics(
        fault_count_90d=fault_count,
        mttr_min_90d=mttr,
        overdue_maintenance_count=int(overdue_maintenance),
        overdue_calibration_count=int(overdue_calibration),
        max_repeat_fault_90d=max_repeat,
    )


def _metrics_to_json(result: HealthScore) -> dict[str, Any]:
    m = result.metrics
    return {
        "fault_count_90d": m.fault_count_90d,
        "mttr_min_90d": m.mttr_min_90d,
        "overdue_maintenance_count": m.overdue_maintenance_count,
        "overdue_calibration_count": m.overdue_calibration_count,
        "max_repeat_fault_90d": m.max_repeat_fault_90d,
        "penalties": m.penalties,
    }


async def generate_daily_snapshots(
    db: AsyncSession, snapshot_date: date | None = None
) -> dict[str, int]:
    """为全部在用/备用设备生成当日健康快照，并执行预警检查。

    幂等：同日重跑按 (equipment_id, snapshot_date) 覆盖更新。
    返回 {total, red, yellow, green, alerts}。
    """
    snapshot_date = snapshot_date or datetime.now(UTC).date()
    weights = await get_score_weights(db)

    equipments = (
        (
            await db.execute(
                select(Equipment).where(
                    Equipment.status.in_(["在用", "备用"]),
                    Equipment.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )

    stats: dict[str, int] = {"total": len(equipments), "g": 0, "y": 0, "r": 0}
    scored_equipments: list[tuple[Equipment, HealthScore]] = []

    for eq in equipments:
        metrics = await collect_metrics(db, eq.id, today=snapshot_date)
        result = compute_health_score(metrics, weights)
        stats[result.grade.lower()] += 1
        scored_equipments.append((eq, result))

        existing = (
            await db.execute(
                select(EquipmentHealthSnapshot).where(
                    EquipmentHealthSnapshot.equipment_id == eq.id,
                    EquipmentHealthSnapshot.snapshot_date == snapshot_date,
                    EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().first()
        if existing:
            existing.score = result.score
            existing.grade = result.grade
            existing.metrics = _metrics_to_json(result)
        else:
            db.add(
                EquipmentHealthSnapshot(
                    equipment_id=eq.id,
                    snapshot_date=snapshot_date,
                    score=result.score,
                    grade=result.grade,
                    metrics=_metrics_to_json(result),
                )
            )

    alert_count = await _run_health_alerts(
        db, snapshot_date, scored_equipments
    )
    return {
        "total": stats["total"],
        "green": stats["g"],
        "yellow": stats["y"],
        "red": stats["r"],
        "alerts": alert_count,
    }


# 重复故障判定阈值：90 天内同症状 ≥3 次
REPEAT_FAULT_THRESHOLD = 3
# 连续红档天数阈值
CONSECUTIVE_RED_DAYS = 2


async def _run_health_alerts(
    db: AsyncSession,
    snapshot_date: date,
    scored_equipments: list[tuple[Equipment, HealthScore]],
) -> int:
    """预警：① 绿/黄→红跳变通知；② 连续红档建议评估；③ 重复故障自动建专项检查单。

    ③ 独立于分档——黄档设备的重复故障同样需要专项检查。
    """
    alerts = 0
    yesterday = snapshot_date - timedelta(days=1)

    for eq, result in scored_equipments:
        if result.grade == "R":
            prev = (
                await db.execute(
                    select(EquipmentHealthSnapshot).where(
                        EquipmentHealthSnapshot.equipment_id == eq.id,
                        EquipmentHealthSnapshot.snapshot_date == yesterday,
                        EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().first()

            if prev is not None and prev.grade in ("G", "Y"):
                # ① 评分绿/黄 → 红跳变，通知（非关键路径）
                alerts += 1
                _schedule_jump_notification(eq, result)
            elif prev is not None and prev.grade == "R":
                # ② 连续红档（今日红 + 昨日红）
                red_streak = await _count_consecutive_red(
                    db, eq.id, snapshot_date
                )
                if red_streak >= CONSECUTIVE_RED_DAYS:
                    alerts += 1
                    _schedule_jump_notification(eq, result)

        # ③ 重复故障 ≥3 次：自动生成专项检查工单（日常维护，走正常建单链路）
        if result.metrics.max_repeat_fault_90d >= REPEAT_FAULT_THRESHOLD:
            created = await _create_repeat_fault_inspection(db, eq, result)
            if created:
                alerts += 1

    return alerts


async def _count_consecutive_red(
    db: AsyncSession, equipment_id: uuid.UUID, snapshot_date: date
) -> int:
    """从当日向前数连续红档天数（含当日）。"""
    rows = (
        (
            await db.execute(
                select(
                    EquipmentHealthSnapshot.snapshot_date,
                    EquipmentHealthSnapshot.grade,
                ).where(
                    EquipmentHealthSnapshot.equipment_id == equipment_id,
                    EquipmentHealthSnapshot.snapshot_date <= snapshot_date,
                    EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                )
                .order_by(EquipmentHealthSnapshot.snapshot_date.desc())
                .limit(CONSECUTIVE_RED_DAYS)
            )
        )
        .all()
    )
    streak = 0
    for row in rows:
        if row.grade == "R":
            streak += 1
        else:
            break
    return streak


async def _create_repeat_fault_inspection(
    db: AsyncSession, eq: Equipment, result: HealthScore
) -> bool:
    """90 天内同症状故障 ≥3 次 → 生成「日常维护」专项检查工单。

    防重：该设备存在未关闭的专项检查工单（描述含健康预警标记）时跳过。
    """
    marker = "【健康预警】"
    open_exists = (
        await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.equipment_id == eq.id,
                WorkOrder.order_type == "日常维护",
                WorkOrder.status.in_(["待处理", "执行中", "待验收"]),
                WorkOrder.fault_description.like(f"{marker}%"),
                WorkOrder.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one()
    if open_exists:
        return False

    from app.modules.equipment.schemas import WorkOrderCreate

    create = WorkOrderCreate(
        equipment_id=eq.id,
        order_type="日常维护",
        priority="高",
        fault_description=(
            f"{marker}近 90 天内同一故障现象重复 "
            f"{result.metrics.max_repeat_fault_90d} 次，请安排专项检查并评估根因"
        ),
    )
    # 责任人缺省走设备负责人（由 create_work_order 内部处理）
    await _create_work_order_safe(db, create)
    return True


async def _create_work_order_safe(
    db: AsyncSession, create: WorkOrderCreate
) -> None:
    """建单失败只记日志，不阻断快照任务。报修人记系统管理员。"""
    from app.modules.equipment.service.work_order import create_work_order
    from app.platform.identity.service import get_or_create_system_admin

    try:
        admin = await get_or_create_system_admin(db)
        await create_work_order(db, create, reporter_id=admin.id)
    except AppException:
        logger.warning("健康预警专项检查工单创建被业务规则拒绝", exc_info=True)
    except Exception:
        logger.exception("健康预警专项检查工单创建失败")


def _schedule_jump_notification(eq: Equipment, result: HealthScore) -> None:
    """评分跳变/连续红通知设备部主管（非关键路径，后台执行）。"""
    import asyncio

    asyncio.ensure_future(_notify_grade_jump(eq, result))


async def _notify_grade_jump(eq: Equipment, result: HealthScore) -> None:
    """评分跳变/连续红：卡片通知该车间的维修群（未配置群则回落日志）。"""
    try:
        from app.modules.equipment.feishu.repair_card import send_card_to_chat
        from app.modules.equipment.service.work_order_feishu import (
            resolve_repair_chat_id,
        )

        chat_id = await resolve_repair_chat_id(eq.workshop_code or "")
        if not chat_id:
            logger.info(
                "健康预警（车间未配置维修群，仅记录）: %s 评分 %.0f",
                eq.name,
                result.score,
            )
            return
        m = result.metrics
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": f"🔴 设备健康预警：{eq.name}（{eq.equipment_no}）",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**健康评分**\n{result.score:.0f}（红档）",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**近90天故障**\n{m.fault_count_90d} 次",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    f"**超期保养**\n"
                                    f"{m.overdue_maintenance_count} 项"
                                ),
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    f"**超期校准**\n"
                                    f"{m.overdue_calibration_count} 项"
                                ),
                            },
                        },
                    ],
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "建议：核查该设备近期重复故障与保养计划执行情况，"
                            "必要时在平台发起专项检查或变动评估。"
                        ),
                    },
                },
            ],
        }
        await send_card_to_chat(chat_id, card)
    except Exception:
        logger.exception("健康预警通知发送失败: %s", eq.name)


# ── 查询接口 ────────────────────────────────────────────────────────


async def get_latest_health(
    db: AsyncSession, equipment_id: uuid.UUID
) -> EquipmentHealthSnapshot | None:
    return (
        (
            await db.execute(
                select(EquipmentHealthSnapshot)
                .where(
                    EquipmentHealthSnapshot.equipment_id == equipment_id,
                    EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                )
                .order_by(EquipmentHealthSnapshot.snapshot_date.desc())
                .limit(30)
            )
        )
        .scalars()
        .first()
    )


async def get_health_trend(
    db: AsyncSession, equipment_id: uuid.UUID, days: int = 30
) -> list[EquipmentHealthSnapshot]:
    start = datetime.now(UTC).date() - timedelta(days=days)
    rows = (
        (
            await db.execute(
                select(EquipmentHealthSnapshot)
                .where(
                    EquipmentHealthSnapshot.equipment_id == equipment_id,
                    EquipmentHealthSnapshot.snapshot_date >= start,
                    EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                )
                .order_by(EquipmentHealthSnapshot.snapshot_date.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_health_board(
    db: AsyncSession,
    workshop_code: str | None = None,
    grade: str | None = None,
) -> list[dict[str, Any]]:
    """健康度榜单：每台设备最新快照 + 基本信息（按评分升序，差在前）。"""
    latest_date = (
        select(func.max(EquipmentHealthSnapshot.snapshot_date))
        .where(EquipmentHealthSnapshot.is_deleted == False)  # noqa: E712
        .scalar_subquery()
    )
    rows = (
        (
            await db.execute(
                select(EquipmentHealthSnapshot, Equipment)
                .join(
                    Equipment,
                    Equipment.id == EquipmentHealthSnapshot.equipment_id,
                )
                .where(
                    EquipmentHealthSnapshot.snapshot_date == latest_date,
                    EquipmentHealthSnapshot.is_deleted == False,  # noqa: E712
                    Equipment.is_deleted == False,  # noqa: E712
                )
                .order_by(EquipmentHealthSnapshot.score.asc())
            )
        )
        .all()
    )
    board: list[dict[str, Any]] = []
    for snap, eq in rows:
        if workshop_code and eq.workshop_code != workshop_code:
            continue
        if grade and snap.grade != grade:
            continue
        board.append(
            {
                "equipment_id": eq.id,
                "equipment_no": eq.equipment_no,
                "equipment_name": eq.name,
                "workshop_code": eq.workshop_code,
                "score": float(snap.score),
                "grade": snap.grade,
                "metrics": snap.metrics,
                "snapshot_date": snap.snapshot_date.isoformat(),
            }
        )
    return board


# ── 维修病历 ────────────────────────────────────────────────────────


async def get_repair_profile(
    db: AsyncSession, equipment_id: uuid.UUID
) -> RepairProfile:
    """查询病历；无记录时只读计算一份瞬态档案（不落库）。"""
    profile = (
        (
            await db.execute(
                select(RepairProfile).where(
                    RepairProfile.equipment_id == equipment_id,
                    RepairProfile.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if profile is not None:
        return profile
    return await _compute_profile_transient(db, equipment_id)


async def _compute_profile_transient(
    db: AsyncSession, equipment_id: uuid.UUID
) -> RepairProfile:
    """按 refresh_repair_profile 的口径只读聚合，返回未入库的瞬态对象。"""
    eq = (
        (
            await db.execute(
                select(Equipment).where(Equipment.id == equipment_id)
            )
        )
        .scalars()
        .first()
    )
    if eq is None:
        raise AppException(message="设备不存在")

    orders = (
        (
            await db.execute(
                select(WorkOrder)
                .where(
                    WorkOrder.equipment_id == equipment_id,
                    WorkOrder.is_deleted == False,  # noqa: E712
                )
                .order_by(WorkOrder.reported_at.desc())
            )
        )
        .scalars()
        .all()
    )
    faults = [o for o in orders if o.order_type == "故障维修"]
    total_faults = len(faults)
    total_downtime = sum(
        o.actual_duration or 0 for o in faults if o.actual_duration
    )
    spare_cost = sum(o.spare_parts_cost or 0 for o in orders)
    mtbf = _calc_mtbf(eq, total_faults)
    return RepairProfile(
        equipment_id=equipment_id,
        total_orders=len(orders),
        total_faults=total_faults,
        total_downtime_min=int(total_downtime),
        total_spare_cost=round(float(spare_cost), 2),
        mtbf_days=mtbf,
        last_3_faults=_last_3_faults(faults),
    )


def _calc_mtbf(eq: Equipment, total_faults: int) -> float | None:
    """MTBF = 入厂天数 / 累计故障数。"""
    if total_faults <= 0 or eq.created_at is None:
        return None
    days = max(
        1,
        (datetime.now(UTC) - eq.created_at).total_seconds() / 86400,
    )
    return round(days / total_faults, 1)


def _last_3_faults(faults: list[WorkOrder]) -> list[dict[str, Any]]:
    return [
        {
            "work_order_no": o.work_order_no,
            "reported_at": o.reported_at.isoformat()
            if o.reported_at
            else None,
            "symptom": None,
            "cause": None,
        }
        for o in faults[:3]
    ]


async def refresh_repair_profile(
    db: AsyncSession, equipment_id: uuid.UUID
) -> RepairProfile:
    """重算设备维修病历（幂等 upsert）。工单闭环后触发。"""
    eq = (
        (
            await db.execute(
                select(Equipment).where(Equipment.id == equipment_id)
            )
        )
        .scalars()
        .first()
    )
    if eq is None:
        raise AppException(message="设备不存在")

    orders = (
        (
            await db.execute(
                select(WorkOrder)
                .where(
                    WorkOrder.equipment_id == equipment_id,
                    WorkOrder.is_deleted == False,  # noqa: E712
                )
                .order_by(WorkOrder.reported_at.desc())
            )
        )
        .scalars()
        .all()
    )
    faults = [o for o in orders if o.order_type == "故障维修"]
    total_faults = len(faults)
    total_downtime = sum(
        o.actual_duration or 0 for o in faults if o.actual_duration
    )
    spare_cost = sum(o.spare_parts_cost or 0 for o in orders)

    profile = (
        (
            await db.execute(
                select(RepairProfile).where(
                    RepairProfile.equipment_id == equipment_id,
                    RepairProfile.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if profile is None:
        profile = RepairProfile(equipment_id=equipment_id)
        db.add(profile)
    profile.total_orders = len(orders)
    profile.total_faults = total_faults
    profile.total_downtime_min = int(total_downtime)
    profile.total_spare_cost = round(float(spare_cost), 2)
    profile.mtbf_days = _calc_mtbf(eq, total_faults)
    profile.last_3_faults = _last_3_faults(faults)
    await db.flush()
    return profile


def schedule_profile_refresh(equipment_id: uuid.UUID) -> None:
    """工单闭环后异步刷新病历（非关键路径，失败只记日志）。"""
    import asyncio

    async def _run() -> None:
        from app.core.database import async_session_factory

        try:
            async with async_session_factory() as db:
                await refresh_repair_profile(db, equipment_id)
                await db.commit()
        except Exception:
            logger.exception("维修病历刷新失败: %s", equipment_id)

    asyncio.ensure_future(_run())
