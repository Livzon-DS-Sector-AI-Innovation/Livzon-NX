"""Tests for maintenance repository layer."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    FailureAction,
    FailureCause,
    FailureSymptom,
    Location,
)
from app.modules.equipment.repository import (
    count_open_work_orders_by_equipment,
    create_failure_code,
    delete_failure_code,
    exists_failure_code_by_code,
    get_failure_code_by_id,
    get_failure_codes,
    get_max_work_order_no,
    update_failure_code,
)
from app.modules.equipment.repository import (
    create_work_order as repo_create_work_order,
)
from app.platform.identity.models import User


@pytest.fixture
def symptom_data() -> dict:
    return {
        "code": "NOISE", "name": "异响",
        "description": "设备运行时发出异常声音", "sort_order": 1,
    }


@pytest.fixture
def cause_data() -> dict:
    return {
        "code": "WEAR", "name": "轴承磨损",
        "description": "轴承因长期使用磨损", "sort_order": 1,
    }


@pytest.fixture
def action_data() -> dict:
    return {
        "code": "REPLACE", "name": "更换部件",
        "description": "更换损坏的部件", "sort_order": 1,
    }


async def test_create_failure_code_symptom(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试创建故障现象"""
    result = await create_failure_code(db_session, FailureSymptom, symptom_data)
    assert result.code == "NOISE"
    assert result.name == "异响"
    assert result.id is not None


async def test_create_failure_code_cause(
    db_session: AsyncSession, cause_data: dict
) -> None:
    """测试创建故障原因"""
    result = await create_failure_code(db_session, FailureCause, cause_data)
    assert result.code == "WEAR"
    assert result.name == "轴承磨损"


async def test_create_failure_code_action(
    db_session: AsyncSession, action_data: dict
) -> None:
    """测试创建维修措施"""
    result = await create_failure_code(db_session, FailureAction, action_data)
    assert result.code == "REPLACE"
    assert result.name == "更换部件"


async def test_get_failure_code_by_id(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试根据ID获取故障代码"""
    created = await create_failure_code(db_session, FailureSymptom, symptom_data)
    result = await get_failure_code_by_id(db_session, FailureSymptom, created.id)
    assert result is not None
    assert result.code == "NOISE"


async def test_get_failure_code_by_id_not_found(
    db_session: AsyncSession,
) -> None:
    """测试获取不存在的故障代码"""
    result = await get_failure_code_by_id(db_session, FailureSymptom, uuid.uuid4())
    assert result is None


async def test_get_failure_codes(
    db_session: AsyncSession,
) -> None:
    """测试获取故障代码列表"""
    await create_failure_code(
        db_session, FailureSymptom, {"code": "NOISE", "name": "异响"}
    )
    await create_failure_code(
        db_session, FailureSymptom, {"code": "LEAK", "name": "泄漏"}
    )
    codes = await get_failure_codes(db_session, FailureSymptom)
    assert len(codes) >= 2


async def test_exists_failure_code_by_code(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试检查故障代码是否存在"""
    await create_failure_code(db_session, FailureSymptom, symptom_data)
    exists = await exists_failure_code_by_code(db_session, FailureSymptom, "NOISE")
    assert exists is True
    not_exists = await exists_failure_code_by_code(db_session, FailureSymptom, "NONE")
    assert not_exists is False


async def test_exists_failure_code_by_code_exclude_id(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试排除自身检查故障代码是否存在"""
    created = await create_failure_code(db_session, FailureSymptom, symptom_data)
    assert (
        await exists_failure_code_by_code(
            db_session, FailureSymptom, "NOISE", exclude_id=created.id
        )
        is False
    )


async def test_update_failure_code(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试更新故障代码"""
    created = await create_failure_code(db_session, FailureSymptom, symptom_data)
    updated = await update_failure_code(
        db_session, FailureSymptom, created.id, {"name": "异常噪音"}
    )
    assert updated is not None
    assert updated.name == "异常噪音"


async def test_delete_failure_code(
    db_session: AsyncSession, symptom_data: dict
) -> None:
    """测试删除故障代码（软删除）"""
    created = await create_failure_code(db_session, FailureSymptom, symptom_data)
    result = await delete_failure_code(db_session, FailureSymptom, created.id)
    assert result is True
    # 验证已被软删除
    found = await get_failure_code_by_id(db_session, FailureSymptom, created.id)
    assert found is None


# ==================== Work Order Repository Tests ====================


async def test_create_work_order(db_session: AsyncSession) -> None:
    """测试创建工单"""
    # 创建用户以满足 reporter_id 外键
    user = User(name="测试用户")
    db_session.add(user)
    await db_session.flush()

    category = EquipmentCategory(name="测试分类", code="T-CAT")
    db_session.add(category)
    await db_session.flush()
    location = Location(name="测试位置", code="T-LOC")
    db_session.add(location)
    await db_session.flush()
    equipment = Equipment(
        equipment_no="EQ-T-CAT-0001",
        name="测试设备",
        category_id=category.id,
        location_id=location.id,
        status="在用",
    )
    db_session.add(equipment)
    await db_session.flush()

    wo = await repo_create_work_order(db_session, {
        "work_order_no": "WO-20260603-0001",
        "equipment_id": equipment.id,
        "order_type": "故障维修",
        "priority": "中",
        "status": "待处理",
        "reporter_id": user.id,
    })
    assert wo.work_order_no == "WO-20260603-0001"
    assert wo.status == "待处理"


async def test_get_max_work_order_no(db_session: AsyncSession) -> None:
    """测试获取最大工单号"""
    result = await get_max_work_order_no(db_session)
    assert result is None or result.startswith("WO-")


async def test_count_open_work_orders_by_equipment(
    db_session: AsyncSession,
) -> None:
    """测试统计设备未关闭工单数"""
    count = await count_open_work_orders_by_equipment(
        db_session, uuid.uuid4()
    )
    assert count == 0
