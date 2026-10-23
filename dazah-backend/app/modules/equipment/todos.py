"""Assigned repair/inspection work, with device department isolation."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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

from app.core.database import get_db
from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.work_order import WorkOrder
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import (
    TodoActor,
    resolve_todo_actor,
    todo_department_ids,
)
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

EquipmentTodoKind = Literal["maintenance", "inspection"]
PAGES = {"maintenance": "equipment:maintenance", "inspection": "equipment:inspection"}
router = APIRouter()


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
            func.concat(WorkOrder.work_order_no, " · ", Equipment.name).label(
                "title"
            ),
            func.concat(
                WorkOrder.status, " · ", WorkOrder.priority, "优先级"
            ).label("detail"),
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


@router.get("/my-todos", response_model=BusinessTodoPage, summary="本人设备待办")
async def equipment_my_todos(
    request: Request,
    user: RequiredUser,
    kind: EquipmentTodoKind,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    workshop: str | None = Query(
        None, pattern=r"^[0-9]{3}(-[0-9])?$", description="车间代码（功能页授权下生效）"
    ),
    db: AsyncSession = Depends(get_db),
) -> BusinessTodoPage:
    key = current_page_key.get() or ""
    if key != PAGES[kind]:
        raise HTTPException(403, "当前页面不能读取其他设备业务的待办")
    # 功能页单页：车间由页内切换块的查询参数指定，缺省回落 201-1
    workshop_code = workshop or "201-1"
    actor = await resolve_todo_actor(request, db, user)
    return await list_equipment_todos(db, kind, actor, page, page_size, workshop_code)
