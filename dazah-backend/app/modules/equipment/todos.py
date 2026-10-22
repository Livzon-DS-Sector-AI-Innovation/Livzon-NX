"""Assigned repair/inspection work, with device department isolation."""


from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.equipment.repository.todos import (
    EquipmentTodoKind,
    list_equipment_todos,
)
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import resolve_todo_actor
from app.shared.todo_schemas import BusinessTodoPage

PAGES = {"maintenance": "equipment:maintenance", "inspection": "equipment:inspection"}
router = APIRouter()


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
