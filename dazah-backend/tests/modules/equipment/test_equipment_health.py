"""设备健康档案（评分/快照/预警/病历）测试。"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    FailureSymptom,
    Location,
    MaintenancePlan,
    WorkOrder,
)
from app.modules.equipment.schemas import WorkOrderCreate
from app.modules.equipment.service import (
    collect_metrics,
    compute_health_score,
    create_work_order,
    generate_daily_snapshots,
    get_health_board,
    get_health_trend,
    refresh_repair_profile,
)
from app.modules.equipment.service.health import (
    GRADE_GREEN_THRESHOLD,
    GRADE_YELLOW_THRESHOLD,
    HealthMetrics,
)
from app.platform.identity.models import User

# ==================== 评分纯函数 ====================


def test_score_all_clean_is_green() -> None:
    result = compute_health_score(HealthMetrics())
    assert result.score == 100.0
    assert result.grade == "G"


def test_score_single_fault() -> None:
    result = compute_health_score(HealthMetrics(fault_count_90d=1))
    # 罚分 = 20 * 0.35 = 7 → 93 分仍为绿
    assert result.score == pytest.approx(93.0)
    assert result.grade == "G"


def test_score_boundaries() -> None:
    # 5 次故障 → 罚 35 分 → 65（黄）
    result = compute_health_score(HealthMetrics(fault_count_90d=5))
    assert result.grade == "Y"
    assert result.score < GRADE_GREEN_THRESHOLD
    # 多项叠加 → 红
    result = compute_health_score(
        HealthMetrics(
            fault_count_90d=5,
            mttr_min_90d=600,
            overdue_maintenance_count=2,
            overdue_calibration_count=1,
            max_repeat_fault_90d=4,
        )
    )
    assert result.grade == "R"
    assert result.score < GRADE_YELLOW_THRESHOLD


def test_score_mttr_tiers() -> None:
    p60 = compute_health_score(HealthMetrics(mttr_min_90d=60)).metrics.penalties["mttr"]
    p241 = compute_health_score(
        HealthMetrics(mttr_min_90d=241)
    ).metrics.penalties["mttr"]
    p600 = compute_health_score(
        HealthMetrics(mttr_min_90d=600)
    ).metrics.penalties["mttr"]
    assert (p60, p241, p600) == (0.0, 60.0, 100.0)


def test_score_repeat_fault_threshold() -> None:
    assert (
        compute_health_score(
            HealthMetrics(max_repeat_fault_90d=2)
        ).metrics.penalties["repeat"]
        == 0.0
    )
    assert (
        compute_health_score(
            HealthMetrics(max_repeat_fault_90d=3)
        ).metrics.penalties["repeat"]
        == 25.0
    )


def test_score_custom_weights() -> None:
    result = compute_health_score(
        HealthMetrics(fault_count_90d=1),
        weights={
            "fault": 1.0,
            "mttr": 0,
            "maintenance": 0,
            "calibration": 0,
            "repeat": 0,
        },
    )
    assert result.score == pytest.approx(80.0)


# ==================== 快照与预警（数据库） ====================


@pytest.fixture
async def health_user(db_session: AsyncSession) -> User:
    user = User(name="健康测试用户", employee_no=f"EMP-H-{uuid4_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


async def _make_equipment(
    db_session: AsyncSession, no: str, status: str = "在用"
) -> Equipment:
    category = EquipmentCategory(name="泵类", code=f"PC-{no}")
    db_session.add(category)
    await db_session.flush()
    location = Location(name="一楼泵房", code=f"LC-{no}")
    db_session.add(location)
    await db_session.flush()
    equipment = Equipment(
        equipment_no=no,
        name=f"离心泵-{no}",
        location_id=location.id,
        status=status,
        workshop_code="201-1",
    )
    db_session.add(equipment)
    await db_session.flush()
    db_session.add(
        EquipmentCategoryLink(equipment_id=equipment.id, category_id=category.id)
    )
    await db_session.flush()
    return equipment


async def _make_fault_order(
    db_session: AsyncSession,
    equipment: Equipment,
    user: User,
    symptom: FailureSymptom | None = None,
    duration: int | None = None,
) -> WorkOrder:
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=equipment.id,
            order_type="故障维修",
            priority="中",
        ),
        reporter_id=user.id,
    )
    if symptom is not None:
        wo.fault_symptom_id = symptom.id
    if duration is not None:
        wo.actual_duration = duration
    # 真实重复故障场景中历史单均已闭环；同时避免下一单触发
    # 「设备维修中不能重复报修」业务守卫
    wo.status = "已关闭"
    equipment.status = "在用"
    await db_session.flush()
    return wo


async def test_collect_metrics_counts_faults(
    db_session: AsyncSession, health_user: User
) -> None:
    eq = await _make_equipment(db_session, "EQ-H-0001")
    symptom = FailureSymptom(code="LEAK", name="泄漏")
    db_session.add(symptom)
    await db_session.flush()
    await _make_fault_order(db_session, eq, health_user, symptom=symptom, duration=30)

    metrics = await collect_metrics(db_session, eq.id)
    assert metrics.fault_count_90d == 1
    assert metrics.mttr_min_90d == 30
    assert metrics.max_repeat_fault_90d == 1


async def test_generate_daily_snapshots_and_alerts(
    db_session: AsyncSession, health_user: User
) -> None:
    """3 次同症状故障 → 快照生成 + 自动建专项检查工单（且不重复建）。"""
    eq = await _make_equipment(db_session, "EQ-H-0002")
    symptom = FailureSymptom(code="NOISE-H", name="异响")
    db_session.add(symptom)
    await db_session.flush()
    for _ in range(3):
        await _make_fault_order(db_session, eq, health_user, symptom=symptom)
    today = date.today()
    stats = await generate_daily_snapshots(db_session, snapshot_date=today)
    assert stats["total"] >= 1
    assert stats["alerts"] >= 1

    # 专项检查工单已创建（日常维护 + 健康预警标记）
    orders = (
        (
            await db_session.execute(
                select(WorkOrder).where(
                    WorkOrder.equipment_id == eq.id,
                    WorkOrder.order_type == "日常维护",
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(
        o.fault_description and o.fault_description.startswith("【健康预警】")
        for o in orders
    )

    # 幂等重跑：不重复建单
    before = len(orders)
    await generate_daily_snapshots(db_session, snapshot_date=today)
    orders_after = (
        (
            await db_session.execute(
                select(WorkOrder).where(
                    WorkOrder.equipment_id == eq.id,
                    WorkOrder.order_type == "日常维护",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(orders_after) == before

    # 同日重跑不产生重复快照
    from app.modules.equipment.models import EquipmentHealthSnapshot

    snaps = (
        (
            await db_session.execute(
                select(EquipmentHealthSnapshot).where(
                    EquipmentHealthSnapshot.equipment_id == eq.id,
                    EquipmentHealthSnapshot.snapshot_date == today,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(snaps) == 1


async def test_health_trend_and_board(
    db_session: AsyncSession, health_user: User
) -> None:
    eq = await _make_equipment(db_session, "EQ-H-0003")
    await generate_daily_snapshots(db_session, snapshot_date=date.today())

    trend = await get_health_trend(db_session, eq.id, days=30)
    assert len(trend) >= 1

    board = await get_health_board(db_session, workshop_code="201-1")
    assert any(item["equipment_id"] == eq.id for item in board)
    board_other = await get_health_board(db_session, workshop_code="999-9")
    assert not any(item["equipment_id"] == eq.id for item in board_other)


async def test_repair_profile_refresh(
    db_session: AsyncSession, health_user: User
) -> None:
    eq = await _make_equipment(db_session, "EQ-H-0004")
    await _make_fault_order(db_session, eq, health_user, duration=120)

    profile = await refresh_repair_profile(db_session, eq.id)
    assert profile.total_faults == 1
    assert profile.total_downtime_min == 120
    assert profile.mtbf_days is not None and profile.mtbf_days > 0
    assert profile.last_3_faults and profile.last_3_faults[0]["work_order_no"]

    # 幂等：再次刷新不产生重复行
    again = await refresh_repair_profile(db_session, eq.id)
    assert again.id == profile.id


async def test_overdue_plan_penalty_in_metrics(
    db_session: AsyncSession, health_user: User
) -> None:
    """超期保养/校准计划计入指标并拉低评分。"""
    from app.modules.equipment.models import CalibrationPlan

    eq = await _make_equipment(db_session, "EQ-H-0005")
    db_session.add(
        MaintenancePlan(
            equipment_id=eq.id,
            plan_name="季度保养",
            plan_type="预防性维护",
            frequency=3,
            frequency_unit="月",
            next_maintenance_date=date.today() - timedelta(days=10),
            status="启用",
        )
    )
    db_session.add(
        CalibrationPlan(
            equipment_id=eq.id,
            calibration_type="内部校准",
            cycle_months=6,
            next_calibration_date=date.today() - timedelta(days=5),
            status="启用",
        )
    )
    await db_session.flush()

    metrics = await collect_metrics(db_session, eq.id)
    assert metrics.overdue_maintenance_count == 1
    assert metrics.overdue_calibration_count == 1

    result = compute_health_score(metrics)
    # 保养罚 50×0.25 + 校准罚 50×0.10 = 17.5 → 82.5 分黄档
    assert result.score == pytest.approx(82.5)
    assert result.grade == "Y"
