"""设备待办查询（工单视角，含部门数据隔离）。"""

from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    Select,
    String,
    and_,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.work_order import WorkOrder
from app.platform.identity.todo_access import TodoActor, todo_department_ids
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

EquipmentTodoKind = Literal["maintenance", "inspection"]


def equipment_todo_query(
    kind: EquipmentTodoKind,
    actor: TodoActor,
    department_ids: set[UUID] | None,
    workshop_code: str = "201-1",
) -> Select[tuple[str, str, str, date | None]] | Select[tuple[str, str, str, date]]:
    valid_equipment = [
        Equipment.is_deleted.is_(False),
        Equipment.workshop_code == workshop_code,
    ]
    if department_ids is not None:
        valid_equipment.append(Equipment.department_id.in_(department_ids))
    personal = or_(
        and_(
            WorkOrder.status.in_(["待处理", "执行中"]),
            or_(
                WorkOrder.assignee_id == actor.user_id,
                and_(
                    WorkOrder.assignee_id.is_(None),
                    WorkOrder.responsible_person_id == actor.user_id,
                ),
            ),
        ),
        and_(WorkOrder.status == "待验收", WorkOrder.reporter_id == actor.user_id),
    )
    return (
        select(
            cast(WorkOrder.id, String).label("id"),
            func.concat(WorkOrder.work_order_no, " · ", Equipment.name).label("title"),
            func.concat(WorkOrder.status, " · ", WorkOrder.priority, "优先级").label(
                "detail"
            ),
            WorkOrder.planned_start_date.label("due_date"),
        )
        .join(Equipment, WorkOrder.equipment_id == Equipment.id)
        .where(WorkOrder.is_deleted.is_(False), *valid_equipment, personal)
    )


async def list_equipment_todos(
    db: AsyncSession,
    kind: EquipmentTodoKind,
    actor: TodoActor,
    page: int,
    page_size: int,
    workshop_code: str = "201-1",
) -> BusinessTodoPage:
    stmt = equipment_todo_query(
        kind, actor, await todo_department_ids(db, actor.scope), workshop_code
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by("due_date", "id").offset((page - 1) * page_size).limit(page_size)
    )
    return BusinessTodoPage(
        items=[BusinessTodoItem.model_validate(row) for row in rows.mappings()],
        total=total,
        page=page,
        page_size=page_size,
    )
