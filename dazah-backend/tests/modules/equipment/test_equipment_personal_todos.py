from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment, Location
from app.modules.equipment.models.work_order import WorkOrder
from app.modules.equipment.todos import PAGES, router
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import Department
from tests.todo_helpers import make_todo_user, scoped_todo_client


async def devices(db: AsyncSession) -> tuple[Department, Equipment, Equipment]:
    suffix = uuid4().hex[:12]
    own = Department(
        id=uuid4(), name=f"授权设备部门{suffix}", feishu_department_id=f"dept-{suffix}"
    )
    other = Department(
        id=uuid4(), name=f"其他设备部门{suffix}", feishu_department_id=f"other-{suffix}"
    )
    location = Location(id=uuid4(), name="测试位置", code=suffix)
    db.add_all([own, other, location])
    await db.flush()
    first = Equipment(
        id=uuid4(),
        name="授权设备",
        equipment_no=f"E-{suffix}",
        location_id=location.id,
        department_id=own.id,
    )
    second = Equipment(
        id=uuid4(),
        name="范围外设备",
        equipment_no=f"F-{suffix}",
        location_id=location.id,
        department_id=other.id,
    )
    db.add_all([first, second])
    await db.flush()
    return own, first, second


@pytest.mark.asyncio
async def test_repairs_follow_assignment_and_acceptance_responsibility(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    other_actor = await make_todo_user(db_session)
    department, own, other = await devices(db_session)
    expected = []
    for variant in (
        "assigned",
        "responsible",
        "reassigned",
        "acceptance",
        "other-acceptance",
        "finished",
        "outside",
    ):
        order = WorkOrder(
            work_order_no=f"W-{uuid4().hex[:15]}",
            equipment_id=other.id if variant == "outside" else own.id,
            order_type="故障维修",
            status="已完成"
            if variant == "finished"
            else "待验收"
            if "acceptance" in variant
            else "待处理",
            responsible_person_id=actor.id,
            assignee_id=other_actor.id
            if variant == "reassigned"
            else None
            if variant == "responsible"
            else actor.id,
            reporter_id=actor.id if variant == "acceptance" else None,
        )
        db_session.add(order)
        await db_session.flush()
        if variant in {"assigned", "responsible", "acceptance"}:
            expected.append(str(order.id))
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "equipment",
        PAGES["maintenance"],
        DepartmentScope(department_names={department.name}),
        monkeypatch,
    ) as client:
        response = await client.get("/api/v1/equipment/my-todos?kind=maintenance")
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} == set(expected)
        # 巡检待办 kind 已下线：请求被参数校验或页面权限层拒绝
        assert (
            await client.get("/api/v1/equipment/my-todos?kind=inspection")
        ).status_code in {403, 422}


@pytest.mark.asyncio
async def test_functional_todos_scope_by_workshop_query(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """设备模块收敛为功能单页：维保待办按车间查询参数过滤。"""
    actor = await make_todo_user(db_session)
    department, first, second = await devices(db_session)
    first.workshop_code = "201-1"
    second.workshop_code = "101-1"
    second.department_id = department.id
    orders = {}
    for code, device in (("201-1", first), ("101-1", second)):
        order = WorkOrder(
            work_order_no=f"scope-{uuid4().hex[:12]}",
            equipment_id=device.id,
            order_type="故障维修",
            status="待处理",
            assignee_id=actor.id,
        )
        db_session.add(order)
        await db_session.flush()
        orders[code] = str(order.id)
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "equipment",
        PAGES["maintenance"],
        DepartmentScope(is_all=True),
        monkeypatch,
    ) as client:
        # 指定车间时仅返回该车间的待办
        for code in ("201-1", "101-1"):
            response = await client.get(
                f"/api/v1/equipment/my-todos?kind=maintenance&workshop={code}"
            )
            assert response.status_code == 200, response.text
            assert {item["id"] for item in response.json()["items"]} == {orders[code]}
            assert response.json()["total"] == 1
        # 不指定车间时缺省回落 201一车间
        default_response = await client.get(
            "/api/v1/equipment/my-todos?kind=maintenance"
        )
        assert default_response.status_code == 200, default_response.text
        assert {item["id"] for item in default_response.json()["items"]} == {
            orders["201-1"]
        }
