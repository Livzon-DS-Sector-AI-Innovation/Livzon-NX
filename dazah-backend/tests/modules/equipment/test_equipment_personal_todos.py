from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment, Location
from app.modules.equipment.models.inspection import InspectionTask
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
async def test_inspection_requires_all_devices_in_scope_and_trusted_assignee(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    other_actor = await make_todo_user(db_session)
    department, own, other = await devices(db_session)
    expected = []
    for variant in (
        "single",
        "multi-own",
        "multi-mixed",
        "missing-device",
        "outside",
        "finished",
        "deleted",
        "other-person",
    ):
        task = InspectionTask(
            task_no=f"I-{uuid4().hex[:15]}",
            equipment_id=other.id if variant == "outside" else own.id,
            assigned_to=other_actor.id if variant == "other-person" else actor.id,
            planned_time=datetime(
                2026, 10, 12, 0, 30, tzinfo=timezone(timedelta(hours=8))
            ),
            status="已完成" if variant == "finished" else "待执行",
            is_deleted=variant == "deleted",
        )
        if variant.startswith("multi") or variant == "missing-device":
            task.equipment_ids = (
                [str(own.id), str(other.id)]
                if variant == "multi-mixed"
                else [str(uuid4())]
                if variant == "missing-device"
                else [str(own.id)]
            )
        db_session.add(task)
        await db_session.flush()
        if variant in {"single", "multi-own"}:
            expected.append(str(task.id))
    async with scoped_todo_client(
        db_session,
        actor,
        router,
        "equipment",
        PAGES["inspection"],
        DepartmentScope(department_names={department.name}),
        monkeypatch,
    ) as client:
        result = await client.get(
            f"/api/v1/equipment/my-todos?kind=inspection&assigned_to={uuid4()}"
        )
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 2
        assert {item["id"] for item in result.json()["items"]} == set(expected)
        assert all(item["due_date"] == "2026-10-12" for item in result.json()["items"])
        paged = await client.get(
            "/api/v1/equipment/my-todos?kind=inspection&page=2&page_size=1"
        )
        assert paged.status_code == 200
        assert paged.json()["total"] == 2 and len(paged.json()["items"]) == 1


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
        assert (
            await client.get("/api/v1/equipment/my-todos?kind=inspection")
        ).status_code == 403


@pytest.mark.asyncio
async def test_workshop_todos_and_legacy_grants_never_include_other_workshops(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_todo_user(db_session)
    department, first, second = await devices(db_session)
    first.workshop_code = "201-1"
    second.workshop_code = "101-1"
    second.department_id = department.id
    tasks = {}
    for code, device in (("201-1", first), ("101-1", second)):
        task = InspectionTask(
            task_no=f"scope-{uuid4().hex[:12]}",
            equipment_id=device.id,
            assigned_to=actor.id,
            planned_time=datetime.now(UTC),
            status="待执行",
        )
        db_session.add(task)
        await db_session.flush()
        tasks[code] = str(task.id)
    for key, code in (
        (PAGES["inspection"], "201-1"),
        ("equipment:workshop-201-1:inspection-201-1", "201-1"),
        ("equipment:workshop-101-1:inspection-101-1", "101-1"),
    ):
        async with scoped_todo_client(
            db_session,
            actor,
            router,
            "equipment",
            key,
            DepartmentScope(is_all=True),
            monkeypatch,
        ) as client:
            response = await client.get(
                "/api/v1/equipment/my-todos?kind=inspection&workshop=203"
            )
            assert response.status_code == 200, response.text
            assert {item["id"] for item in response.json()["items"]} == {tasks[code]}
            assert response.json()["total"] == 1
            refused = await client.get(
                "/api/v1/equipment/my-todos?kind=inspection",
                headers={"X-Dazah-Page-Key": "equipment:workshop-203:inspection-203"},
            )
            assert refused.status_code == 403
