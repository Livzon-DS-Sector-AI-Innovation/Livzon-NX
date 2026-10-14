"""Personally owned registration audit work; shared ledgers are not assignments."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Date, String, case, cast, false, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.registration.models.validation_audit import ValidationAuditTask
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import TodoActor, resolve_todo_actor
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

PAGES = {
    "validation-audits": (
        "registration:project:declaration-progress:international-planned-in-progress"
    )
}
router = APIRouter()


async def list_registration_todos(
    db: AsyncSession, actor: TodoActor, page: int, page_size: int
) -> BusinessTodoPage:
    stmt = select(
        cast(ValidationAuditTask.id, String).label("id"),
        func.concat(
            ValidationAuditTask.product_name, " · ", ValidationAuditTask.task_name
        ).label("title"),
        case(
            (ValidationAuditTask.status == "draft", "待上传审核文件"),
            (ValidationAuditTask.status == "failed", "审核失败，待检查并重试"),
            else_="待解析并审核",
        ).label("detail"),
        literal(None, type_=Date).label("due_date"),
    ).where(
        ValidationAuditTask.is_deleted.is_(False),
        ValidationAuditTask.created_by == actor.user_id,
        ValidationAuditTask.status.in_(["draft", "uploaded", "failed"]),
        # Audit tasks have no department column. Do not guess ownership when a
        # future grant restricts departments; current registration pages use all.
        literal(True) if actor.scope.is_all else false(),
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by("id").offset((page - 1) * page_size).limit(page_size)
    )
    return BusinessTodoPage(
        items=[BusinessTodoItem.model_validate(row) for row in rows.mappings()],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/my-todos", response_model=BusinessTodoPage, summary="本人注册待办")
async def registration_my_todos(
    request: Request,
    user: RequiredUser,
    kind: Literal["validation-audits"],
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> BusinessTodoPage:
    if current_page_key.get() != PAGES[kind]:
        raise HTTPException(403, "当前页面不能读取其他注册业务的待办")
    return await list_registration_todos(
        db, await resolve_todo_actor(request, db, user), page, page_size
    )
