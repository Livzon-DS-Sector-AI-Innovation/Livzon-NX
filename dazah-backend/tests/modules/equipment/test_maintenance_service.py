"""Tests for maintenance service layer (failure code and work order functions)."""

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, DuplicateException, NotFoundException
from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    FailureSymptom,
    Location,
)
from app.modules.equipment.schemas import (
    CalibrationPlanCreate,
    CalibrationRecordCreate,
    FailureCodeCreate,
    FailureCodeUpdate,
    WorkOrderComplete,
    WorkOrderCreate,
    WorkOrderVerify,
)
from app.modules.equipment.service import (
    assign_work_order,
    close_work_order,
    complete_work_order,
    create_calibration_plan,
    create_calibration_record,
    create_failure_code,
    create_work_order,
    delete_failure_code,
    generate_work_order_no,
    get_calibration_plan_by_id,
    get_calibration_record_by_id,
    get_failure_code_by_id,
    get_failure_codes,
    start_work_order,
    update_failure_code,
    verify_work_order,
)
from app.platform.identity.models import User


@pytest.fixture
def sample_symptom_data() -> FailureCodeCreate:
    return FailureCodeCreate(
        code="NOISE",
        name="异响",
        description="设备运行时发出异常声音",
        sort_order=1,
    )


async def test_create_failure_code_success(
    db_session: AsyncSession, sample_symptom_data: FailureCodeCreate
) -> None:
    """测试成功创建故障代码"""
    result = await create_failure_code(
        db_session, FailureSymptom, sample_symptom_data
    )
    assert result.code == "NOISE"
    assert result.name == "异响"
    assert result.id is not None


async def test_create_failure_code_duplicate(
    db_session: AsyncSession, sample_symptom_data: FailureCodeCreate
) -> None:
    """测试创建重复故障代码抛出异常"""
    await create_failure_code(db_session, FailureSymptom, sample_symptom_data)
    with pytest.raises(DuplicateException):
        await create_failure_code(db_session, FailureSymptom, sample_symptom_data)


async def test_get_failure_code_by_id_success(
    db_session: AsyncSession, sample_symptom_data: FailureCodeCreate
) -> None:
    """测试根据ID获取故障代码"""
    created = await create_failure_code(
        db_session, FailureSymptom, sample_symptom_data
    )
    result = await get_failure_code_by_id(
        db_session, FailureSymptom, created.id
    )
    assert result.id == created.id
    assert result.code == "NOISE"


async def test_get_failure_code_by_id_not_found(
    db_session: AsyncSession,
) -> None:
    """测试获取不存在的故障代码抛出异常"""
    with pytest.raises(NotFoundException):
        await get_failure_code_by_id(db_session, FailureSymptom, uuid.uuid4())


async def test_update_failure_code_success(
    db_session: AsyncSession, sample_symptom_data: FailureCodeCreate
) -> None:
    """测试成功更新故障代码"""
    created = await create_failure_code(
        db_session, FailureSymptom, sample_symptom_data
    )
    updated = await update_failure_code(
        db_session,
        FailureSymptom,
        created.id,
        FailureCodeUpdate(name="异常噪音", sort_order=2),
    )
    assert updated.name == "异常噪音"
    assert updated.sort_order == 2
    assert updated.code == "NOISE"


async def test_delete_failure_code_success(
    db_session: AsyncSession, sample_symptom_data: FailureCodeCreate
) -> None:
    """测试成功删除故障代码"""
    created = await create_failure_code(
        db_session, FailureSymptom, sample_symptom_data
    )
    result = await delete_failure_code(
        db_session, FailureSymptom, created.id
    )
    assert result is True
    # 验证已被软删除
    with pytest.raises(NotFoundException):
        await get_failure_code_by_id(db_session, FailureSymptom, created.id)


async def test_get_failure_codes_list(
    db_session: AsyncSession,
) -> None:
    """测试获取故障代码列表"""
    await create_failure_code(
        db_session,
        FailureSymptom,
        FailureCodeCreate(code="NOISE", name="异响"),
    )
    await create_failure_code(
        db_session,
        FailureSymptom,
        FailureCodeCreate(code="LEAK", name="泄漏"),
    )
    codes = await get_failure_codes(db_session, FailureSymptom)
    assert len(codes) >= 2


# ==================== Work Order Service Tests ====================


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """创建测试用用户"""
    user = User(name="测试用户", employee_no="EMP-TEST-001")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def sample_equipment(db_session: AsyncSession) -> Equipment:
    """创建测试用设备"""
    category = EquipmentCategory(name="反应釜", code="RF-TEST")
    db_session.add(category)
    await db_session.flush()

    location = Location(name="一车间", code="WS-TEST")
    db_session.add(location)
    await db_session.flush()

    equipment = Equipment(
        equipment_no="EQ-RF-TEST-0001",
        name="R-101反应釜",
        category_id=category.id,
        location_id=location.id,
        status="在用",
    )
    db_session.add(equipment)
    await db_session.flush()
    return equipment


async def test_generate_work_order_no(db_session: AsyncSession) -> None:
    """测试生成工单号"""
    wo_no = await generate_work_order_no(db_session)
    assert wo_no.startswith("WO-")
    assert len(wo_no) == 16  # WO-yyyyMMdd-0001 (3+8+1+4)


async def test_create_work_order(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试创建工单"""
    data = WorkOrderCreate(
        equipment_id=sample_equipment.id,
        order_type="故障维修",
        priority="高",
        fault_description="设备发出异响",
    )
    wo = await create_work_order(db_session, data, sample_user.id)
    assert wo.work_order_no.startswith("WO-")
    assert wo.status == "待处理"
    assert wo.equipment_id == sample_equipment.id


async def test_create_work_order_equipment_not_in_service(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试设备不在用时不能创建工单"""
    sample_equipment.status = "维修中"
    await db_session.flush()

    data = WorkOrderCreate(equipment_id=sample_equipment.id)
    with pytest.raises(AppException):
        await create_work_order(db_session, data, sample_user.id)


async def test_work_order_lifecycle(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试工单完整生命周期：创建 → 指派 → 开始 → 完成 → 验收 → 关闭"""
    assignee = User(name="维修员", employee_no="EMP-TEST-002")
    verifier = User(name="验收员", employee_no="EMP-TEST-003")
    db_session.add_all([assignee, verifier])
    await db_session.flush()

    # 创建
    data = WorkOrderCreate(
        equipment_id=sample_equipment.id,
        fault_description="设备异响",
    )
    wo = await create_work_order(db_session, data, sample_user.id)
    assert wo.status == "待处理"

    # 指派
    wo = await assign_work_order(db_session, wo.id, assignee.id)
    assert wo.status == "待处理"
    assert wo.assignee_id == assignee.id

    # 开始
    wo = await start_work_order(db_session, wo.id)
    assert wo.status == "执行中"
    assert wo.started_at is not None

    # 完成
    wo = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="更换了轴承")
    )
    assert wo.status == "待验收"
    assert wo.completed_at is not None
    assert wo.actual_duration is not None

    # 验收通过
    wo = await verify_work_order(
        db_session, wo.id, verifier.id, WorkOrderVerify(result="合格")
    )
    assert wo.status == "已完成"
    assert wo.verification_result == "合格"

    # 关闭
    wo = await close_work_order(db_session, wo.id)
    assert wo.status == "已关闭"


async def test_work_order_verify_reject(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试验收不通过打回重修"""
    assignee = User(name="维修员", employee_no="EMP-TEST-004")
    verifier = User(name="验收员", employee_no="EMP-TEST-005")
    db_session.add_all([assignee, verifier])
    await db_session.flush()

    data = WorkOrderCreate(equipment_id=sample_equipment.id)
    wo = await create_work_order(db_session, data, sample_user.id)
    wo = await assign_work_order(db_session, wo.id, assignee.id)
    wo = await start_work_order(db_session, wo.id)
    wo = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="简单处理")
    )

    # 验收不通过
    wo = await verify_work_order(
        db_session,
        wo.id,
        verifier.id,
        WorkOrderVerify(result="不合格", remark="问题未解决"),
    )
    assert wo.status == "执行中"
    assert wo.verification_result == "不合格"


async def test_work_order_invalid_transition(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试非法状态转换"""
    data = WorkOrderCreate(equipment_id=sample_equipment.id)
    wo = await create_work_order(db_session, data, sample_user.id)

    # 待处理不能直接开始维修
    with pytest.raises(AppException):
        await start_work_order(db_session, wo.id)


# ==================== Calibration Service Tests ====================


async def test_create_calibration_plan(
    db_session: AsyncSession, sample_equipment: Equipment
) -> None:
    """测试创建校准计划"""
    data = CalibrationPlanCreate(
        equipment_id=sample_equipment.id,
        calibration_type="内部校准",
        cycle_months=6,
        last_calibration_date=date(2026, 1, 1),
    )
    plan = await create_calibration_plan(db_session, data)
    assert plan.calibration_type == "内部校准"
    assert plan.cycle_months == 6
    assert plan.next_calibration_date == date(2026, 7, 1)


async def test_create_calibration_plan_without_last_date(
    db_session: AsyncSession, sample_equipment: Equipment
) -> None:
    """测试创建校准计划（无上次校准日期时不自动计算下次日期）"""
    data = CalibrationPlanCreate(
        equipment_id=sample_equipment.id,
        calibration_type="外部检定",
        cycle_months=12,
    )
    plan = await create_calibration_plan(db_session, data)
    assert plan.next_calibration_date is None


async def test_get_calibration_plan_by_id(
    db_session: AsyncSession, sample_equipment: Equipment
) -> None:
    """测试根据ID获取校准计划"""
    data = CalibrationPlanCreate(
        equipment_id=sample_equipment.id,
        calibration_type="内部校准",
        cycle_months=6,
    )
    created = await create_calibration_plan(db_session, data)
    result = await get_calibration_plan_by_id(db_session, created.id)
    assert result.id == created.id
    assert result.calibration_type == "内部校准"


async def test_get_calibration_plan_not_found(
    db_session: AsyncSession,
) -> None:
    """测试获取不存在的校准计划抛出异常"""
    with pytest.raises(NotFoundException):
        await get_calibration_plan_by_id(db_session, uuid.uuid4())


async def test_create_calibration_record_updates_plan(
    db_session: AsyncSession, sample_equipment: Equipment
) -> None:
    """测试创建校准记录后自动更新计划日期"""
    plan_data = CalibrationPlanCreate(
        equipment_id=sample_equipment.id,
        calibration_type="内部校准",
        cycle_months=6,
        last_calibration_date=date(2026, 1, 1),
    )
    plan = await create_calibration_plan(db_session, plan_data)

    record_data = CalibrationRecordCreate(
        calibration_plan_id=plan.id,
        calibration_date=date(2026, 7, 1),
        calibration_type="内部校准",
        result="合格",
    )
    record = await create_calibration_record(db_session, record_data)
    assert record.next_due_date == date(2027, 1, 1)
    assert record.equipment_id == sample_equipment.id

    # 验证计划日期已更新
    await db_session.refresh(plan)
    assert plan.last_calibration_date == date(2026, 7, 1)
    assert plan.next_calibration_date == date(2027, 1, 1)


async def test_get_calibration_record_by_id(
    db_session: AsyncSession, sample_equipment: Equipment
) -> None:
    """测试根据ID获取校准记录"""
    plan_data = CalibrationPlanCreate(
        equipment_id=sample_equipment.id,
        calibration_type="内部校准",
        cycle_months=6,
        last_calibration_date=date(2026, 1, 1),
    )
    plan = await create_calibration_plan(db_session, plan_data)

    record_data = CalibrationRecordCreate(
        calibration_plan_id=plan.id,
        calibration_date=date(2026, 7, 1),
        calibration_type="内部校准",
        result="合格",
    )
    created = await create_calibration_record(db_session, record_data)
    result = await get_calibration_record_by_id(db_session, created.id)
    assert result.id == created.id
    assert result.result == "合格"


async def test_get_calibration_record_not_found(
    db_session: AsyncSession,
) -> None:
    """测试获取不存在的校准记录抛出异常"""
    with pytest.raises(NotFoundException):
        await get_calibration_record_by_id(db_session, uuid.uuid4())


async def test_maintenance_work_order_lifecycle(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试计划维护工单生命周期：创建 → 指派 → 执行 → 完成 → 关闭"""
    assignee = User(name="维护员", employee_no="EMP-MAINT-001")
    db_session.add(assignee)
    await db_session.flush()

    # 创建
    data = WorkOrderCreate(
        equipment_id=sample_equipment.id,
        order_type="计划维护",
        planned_start_date=date(2026, 6, 10),
    )
    wo = await create_work_order(db_session, data, sample_user.id)
    assert wo.status == "待处理"

    # 指派
    wo = await assign_work_order(db_session, wo.id, assignee.id)
    assert wo.status == "待处理"

    # 开始执行
    wo = await start_work_order(db_session, wo.id)
    assert wo.status == "执行中"

    # 完成（跳过验收）
    wo = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="更换润滑油，检查密封")
    )
    assert wo.status == "已完成"

    # 关闭
    wo = await close_work_order(db_session, wo.id)
    assert wo.status == "已关闭"


async def test_inspection_work_order_lifecycle(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试巡检工单生命周期"""
    data = WorkOrderCreate(
        equipment_id=sample_equipment.id,
        order_type="巡检",
    )
    wo = await create_work_order(db_session, data, sample_user.id)
    assert wo.status == "待处理"

    wo = await start_work_order(db_session, wo.id)
    assert wo.status == "执行中"

    wo = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="巡检完成")
    )
    assert wo.status == "已完成"


async def test_verify_not_allowed_for_maintenance(
    db_session: AsyncSession,
    sample_equipment: Equipment,
    sample_user: User,
) -> None:
    """测试计划维护工单不能验收"""
    verifier = User(name="验收员", employee_no="EMP-VERIFY-001")
    db_session.add(verifier)
    await db_session.flush()

    data = WorkOrderCreate(
        equipment_id=sample_equipment.id,
        order_type="计划维护",
    )
    wo = await create_work_order(db_session, data, sample_user.id)
    wo = await start_work_order(db_session, wo.id)
    wo = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="维护完成")
    )

    with pytest.raises(AppException):
        await verify_work_order(
            db_session, wo.id, verifier.id, WorkOrderVerify(result="合格")
        )
