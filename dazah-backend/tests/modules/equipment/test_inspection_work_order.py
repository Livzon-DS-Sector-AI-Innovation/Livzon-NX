"""Tests for inspection anomaly auto work-order creation and close-task gating."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models import Equipment, Location, WorkOrder
from app.modules.equipment.models.inspection_template import (
    InspectionTemplate,
    InspectionTemplateItem,
)
from app.modules.equipment.repository.work_order import (
    get_pending_work_orders_by_inspection_task,
)
from app.modules.equipment.service.inspection import (
    close_task,
    complete_task,
    create_task,
    start_task,
    submit_equipment_check,
)
from app.platform.identity.models import Department, User


# ═══════════ Fixtures ═══════════════════════════════════════


@pytest.fixture(autouse=True)
def _mock_notifications():
    """Mock all Feishu notification calls so tests don't hit external APIs."""
    with (
        patch(
            "app.modules.equipment.service.inspection_notification."
            "send_inspection_start_notification",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.equipment.service.inspection_notification."
            "send_work_order_notification",
            new_callable=AsyncMock,
        ),
    ):
        yield


@pytest.fixture
async def inspector(db_session: AsyncSession) -> User:
    user = User(name="巡检员", employee_no=f"EMP-INS-{uuid.uuid4().hex[:8]}")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def leader(db_session: AsyncSession) -> User:
    user = User(
        name="部门负责人",
        employee_no=f"EMP-LDR-{uuid.uuid4().hex[:8]}",
        feishu_open_id=f"ou_test_leader_{uuid.uuid4().hex[:6]}",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def department(db_session: AsyncSession, leader: User) -> Department:
    dept = Department(
        name="生产一部",
        feishu_department_id=f"od_test_dept_{uuid.uuid4().hex[:6]}",
        leader_user_id=leader.feishu_open_id,
    )
    db_session.add(dept)
    await db_session.flush()
    return dept


@pytest.fixture
async def equipment_with_dept(
    db_session: AsyncSession, department: Department
) -> Equipment:
    location = Location(name="一车间", code=f"WS-{uuid.uuid4().hex[:6]}")
    db_session.add(location)
    await db_session.flush()
    eq = Equipment(
        equipment_no=f"EQ-{uuid.uuid4().hex[:8]}",
        name="R-101反应釜",
        location_id=location.id,
        status="在用",
        importance="高",
        department_id=department.id,
    )
    db_session.add(eq)
    await db_session.flush()
    return eq


@pytest.fixture
async def template_with_items(db_session: AsyncSession) -> InspectionTemplate:
    tpl = InspectionTemplate(name="巡检模板测试")
    db_session.add(tpl)
    await db_session.flush()
    items = [
        InspectionTemplateItem(
            template_id=tpl.id,
            item_name="温度检查",
            expected_result="正常范围",
            sort_order=1,
        ),
        InspectionTemplateItem(
            template_id=tpl.id,
            item_name="密封性",
            expected_result="无渗漏",
            sort_order=2,
        ),
    ]
    db_session.add_all(items)
    await db_session.flush()
    return tpl


async def _get_template_items(
    db: AsyncSession, template_id: uuid.UUID
) -> list[InspectionTemplateItem]:
    """Helper: fetch template items for building record dicts."""
    result = await db.execute(
        select(InspectionTemplateItem).where(
            InspectionTemplateItem.template_id == template_id,
        )
    )
    return list(result.scalars().all())


@pytest.fixture
async def inspection_task(
    db_session: AsyncSession,
    inspector: User,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    from datetime import datetime, UTC

    task = await create_task(
        db_session,
        {
            "plan_type": "设备巡检",
            "equipment_id": equipment_with_dept.id,
            "template_ids": [template_with_items.id],
            "assigned_to": inspector.id,
            "planned_time": datetime.now(UTC),
        },
    )
    task = await start_task(db_session, task.id)
    return task


# ═══════════ Tests ═══════════════════════════════════════════


async def test_submit_with_anomaly_creates_work_order(
    db_session: AsyncSession,
    inspection_task,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    """提交含异常结果的检查记录应自动创建工单。"""
    items = await _get_template_items(db_session, template_with_items.id)

    records = [
        {
            "template_item_id": items[0].id,
            "result": "异常",
            "remark": "温度超标",
        },
        {
            "template_item_id": items[1].id,
            "result": "正常",
        },
    ]

    created = await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )
    assert len(created) == 2

    # 应创建一个异常处理工单
    pending = await get_pending_work_orders_by_inspection_task(
        db_session, inspection_task.id
    )
    assert len(pending) == 1
    wo = pending[0]
    assert wo.order_type == "异常处理"
    assert wo.status == "待处理"
    assert wo.equipment_id == equipment_with_dept.id
    assert wo.inspection_task_id == inspection_task.id
    assert wo.priority == "高"
    assert "温度检查" in (wo.fault_description or "")
    # 责任人应为部门负责人对应的 User.id
    assert wo.responsible_person_id is not None


async def test_submit_all_normal_no_work_order(
    db_session: AsyncSession,
    inspection_task,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    """全部正常的检查结果不应创建工单。"""
    items = await _get_template_items(db_session, template_with_items.id)

    records = [
        {"template_item_id": items[0].id, "result": "正常"},
        {"template_item_id": items[1].id, "result": "正常"},
    ]

    created = await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )
    assert len(created) == 2

    pending = await get_pending_work_orders_by_inspection_task(
        db_session, inspection_task.id
    )
    assert len(pending) == 0


async def test_duplicate_work_order_not_created(
    db_session: AsyncSession,
    inspection_task,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    """重复提交异常结果不应创建重复工单。"""
    items = await _get_template_items(db_session, template_with_items.id)

    records = [
        {"template_item_id": items[0].id, "result": "异常", "remark": "温度超标"},
    ]

    # 第一次提交
    await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )

    # 第二次提交（同一任务+同一设备）
    await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )

    # 应只有一个工单
    pending = await get_pending_work_orders_by_inspection_task(
        db_session, inspection_task.id
    )
    assert len(pending) == 1


async def test_close_blocked_by_pending_work_order(
    db_session: AsyncSession,
    inspection_task,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    """存在未处理工单时关闭巡检任务应抛出 AppException。"""
    items = await _get_template_items(db_session, template_with_items.id)

    records = [
        {"template_item_id": items[0].id, "result": "异常", "remark": "温度超标"},
    ]
    await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )

    # 先完成任务
    await complete_task(db_session, inspection_task.id)

    # 尝试关闭任务，应被工单阻塞
    with pytest.raises(AppException) as exc_info:
        await close_task(db_session, inspection_task.id)
    assert "未处理" in exc_info.value.message
    assert exc_info.value.detail_msg is not None
    assert len(exc_info.value.detail_msg["pending_work_orders"]) == 1


async def test_close_succeeds_after_work_order_closed(
    db_session: AsyncSession,
    inspection_task,
    equipment_with_dept: Equipment,
    template_with_items: InspectionTemplate,
):
    """所有关联工单关闭后，巡检任务可以正常关闭。"""
    items = await _get_template_items(db_session, template_with_items.id)

    records = [
        {"template_item_id": items[0].id, "result": "异常", "remark": "温度超标"},
    ]
    await submit_equipment_check(
        db_session,
        inspection_task.id,
        equipment_with_dept.id,
        records,
    )

    # 完成任务
    await complete_task(db_session, inspection_task.id)

    # 直接将工单状态设为"已关闭"（测试关注点是 close_task 的行为）
    await db_session.execute(
        update(WorkOrder)
        .where(WorkOrder.inspection_task_id == inspection_task.id)
        .values(status="已关闭")
    )
    await db_session.flush()

    # 关闭巡检任务应成功
    closed_task = await close_task(db_session, inspection_task.id)
    assert closed_task.status == "已关闭"


async def test_work_order_no_responsible_person(
    db_session: AsyncSession,
    inspector: User,
    template_with_items: InspectionTemplate,
):
    """设备没有归属部门时，工单仍应创建但责任人为 None。"""
    # 创建无部门的设备
    location = Location(name="二车间", code=f"WS-{uuid.uuid4().hex[:6]}")
    db_session.add(location)
    await db_session.flush()
    eq_no_dept = Equipment(
        equipment_no=f"EQ-{uuid.uuid4().hex[:8]}",
        name="R-202反应釜",
        location_id=location.id,
        status="在用",
        importance="中",
        department_id=None,
    )
    db_session.add(eq_no_dept)
    await db_session.flush()

    from datetime import datetime, UTC

    # 创建任务并启动
    task = await create_task(
        db_session,
        {
            "plan_type": "设备巡检",
            "equipment_id": eq_no_dept.id,
            "template_ids": [template_with_items.id],
            "assigned_to": inspector.id,
            "planned_time": datetime.now(UTC),
        },
    )
    task = await start_task(db_session, task.id)

    # 提交异常
    items = await _get_template_items(db_session, template_with_items.id)
    records = [
        {"template_item_id": items[0].id, "result": "异常", "remark": "温度异常"},
    ]
    await submit_equipment_check(db_session, task.id, eq_no_dept.id, records)

    # 工单应创建，但责任人为 None
    pending = await get_pending_work_orders_by_inspection_task(
        db_session, task.id
    )
    assert len(pending) == 1
    wo = pending[0]
    assert wo.responsible_person_id is None
    assert wo.priority == "中"
