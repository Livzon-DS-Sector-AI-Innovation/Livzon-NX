"""Tests for equipment service layer."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, DuplicateException, NotFoundException
from app.modules.equipment.models.inspection import InspectionTask
from app.modules.equipment.schemas import (
    EquipmentCategoryCreate,
    EquipmentCategoryUpdate,
)
from app.modules.equipment.service import (
    create_equipment_category,
    delete_equipment_category,
    generate_equipment_no,
    get_equipment_category_by_id,
    update_equipment_category,
)


@pytest.fixture
def sample_category_data() -> EquipmentCategoryCreate:
    return EquipmentCategoryCreate(
        name="反应釜",
        code="RF",
        description="反应设备",
    )


async def test_create_equipment_category_success(
    db_session: AsyncSession, sample_category_data: EquipmentCategoryCreate
) -> None:
    """测试成功创建设备分类"""
    category = await create_equipment_category(db_session, sample_category_data)
    assert category.name == "反应釜"
    assert category.code == "RF"


async def test_create_equipment_category_duplicate_code(
    db_session: AsyncSession, sample_category_data: EquipmentCategoryCreate
) -> None:
    """测试创建重复编码的设备分类"""
    await create_equipment_category(db_session, sample_category_data)
    with pytest.raises(DuplicateException):
        await create_equipment_category(db_session, sample_category_data)


async def test_get_equipment_category_not_found(db_session: AsyncSession) -> None:
    """测试获取不存在的设备分类"""
    with pytest.raises(NotFoundException):
        await get_equipment_category_by_id(db_session, uuid.uuid4())


async def test_update_equipment_category_success(
    db_session: AsyncSession, sample_category_data: EquipmentCategoryCreate
) -> None:
    """测试成功更新设备分类"""
    category = await create_equipment_category(db_session, sample_category_data)
    updated = await update_equipment_category(
        db_session,
        category.id,
        EquipmentCategoryUpdate(name="大型反应釜"),
    )
    assert updated.name == "大型反应釜"


async def test_delete_equipment_category_success(
    db_session: AsyncSession, sample_category_data: EquipmentCategoryCreate
) -> None:
    """测试成功删除设备分类"""
    category = await create_equipment_category(db_session, sample_category_data)
    result = await delete_equipment_category(db_session, category.id)
    assert result is True


async def test_generate_equipment_no(
    db_session: AsyncSession, sample_category_data: EquipmentCategoryCreate
) -> None:
    """测试生成设备编号"""
    category = await create_equipment_category(db_session, sample_category_data)
    equipment_no = await generate_equipment_no(db_session, category.code)
    assert equipment_no == "EQ-RF-0001"


# ---------- 巡检任务创建校验（设备/模板绑定） ----------


async def test_create_task_requires_equipment(db_session: AsyncSession) -> None:
    from app.modules.equipment.service import inspection as inspection_svc

    with pytest.raises(AppException, match="至少需要选择一台设备"):
        await inspection_svc.create_task(
            db_session, {"planned_time": "2026-10-10T08:00:00"}
        )


async def test_create_task_rejects_template_keys_outside_selection(
    db_session: AsyncSession,
) -> None:
    import uuid as uuid_mod

    from app.modules.equipment.service import inspection as inspection_svc

    chosen = str(uuid_mod.uuid4())
    stranger = str(uuid_mod.uuid4())
    with pytest.raises(AppException, match="不在已选择的设备列表中"):
        await inspection_svc.create_task(
            db_session,
            {
                "equipment_ids": [chosen],
                "equipment_templates": {stranger: [str(uuid_mod.uuid4())]},
                "planned_time": "2026-10-10T08:00:00",
            },
        )


async def test_create_task_requires_template_binding(db_session: AsyncSession) -> None:
    import uuid as uuid_mod

    from app.modules.equipment.service import inspection as inspection_svc

    chosen_a = str(uuid_mod.uuid4())
    chosen_b = str(uuid_mod.uuid4())
    with pytest.raises(AppException, match="必须绑定至少一个检查模板"):
        await inspection_svc.create_task(
            db_session,
            {
                "equipment_ids": [chosen_a, chosen_b],
                "equipment_templates": {chosen_a: [str(uuid_mod.uuid4())]},
                "planned_time": "2026-10-10T08:00:00",
            },
        )
    with pytest.raises(AppException, match="必须选择检查模板"):
        await inspection_svc.create_task(
            db_session,
            {
                "equipment_ids": [str(uuid_mod.uuid4())],
                "planned_time": "2026-10-10T08:00:00",
            },
        )


async def test_submit_route_check_completes_task_with_given_result(
    db_session: AsyncSession,
) -> None:
    """线路巡检提交：总体结果来自飞书侧判定，直接落库并完成。"""
    from app.modules.equipment.service import inspection as inspection_svc

    task = InspectionTask(
        task_no=f"I-{uuid.uuid4().hex[:15]}",
        planned_time=datetime(2026, 10, 15, 8, 0, tzinfo=UTC),
        status="执行中",
    )
    db_session.add(task)
    await db_session.flush()

    completed = await inspection_svc.submit_route_check(
        db_session, task.id, overall_result="正常"
    )
    assert completed.status == "已完成"
    assert completed.overall_result == "正常"
    assert completed.completed_at is not None

    with pytest.raises(AppException):
        # 已完成的任务不允许再次提交
        await inspection_svc.submit_route_check(
            db_session, task.id, overall_result="正常"
        )


async def test_submit_route_check_rejects_pending_task(
    db_session: AsyncSession,
) -> None:
    from app.modules.equipment.service import inspection as inspection_svc

    task = InspectionTask(
        task_no=f"I-{uuid.uuid4().hex[:15]}",
        planned_time=datetime(2026, 10, 15, 8, 0, tzinfo=UTC),
        status="待执行",
    )
    db_session.add(task)
    await db_session.flush()

    with pytest.raises(AppException, match="状态不允许"):
        await inspection_svc.submit_route_check(
            db_session, task.id, overall_result="正常"
        )
