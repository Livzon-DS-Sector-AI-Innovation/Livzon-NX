"""Personal training follow-up, in addition to existing transfer approvals."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Date, String, cast, false, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.hr.models import PlanTrackingRecord
from app.modules.hr.service import PositionTransferRecordService
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import TodoActor, resolve_todo_actor
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

PAGES = {
    "plan-tracking": "hr:training:plan-tracking",
    "position-transfer": "hr:position-transfer",
}
router = APIRouter()


async def list_hr_todos(
    db: AsyncSession, actor: TodoActor, page: int, page_size: int
) -> BusinessTodoPage:
    stmt = select(
        cast(PlanTrackingRecord.id, String).label("id"),
        func.coalesce(PlanTrackingRecord.training_content, "培训计划跟踪").label(
            "title"
        ),
        func.concat(
            PlanTrackingRecord.year, "年 ", PlanTrackingRecord.month, "月 · 待跟踪完成"
        ).label("detail"),
        literal(None, type_=Date).label("due_date"),
    ).where(
        PlanTrackingRecord.is_deleted.is_(False),
        PlanTrackingRecord.is_completed.is_not(True),
        PlanTrackingRecord.tracker == actor.unique_name
        if actor.unique_name
        else false(),
    )
    if not actor.scope.is_all:
        stmt = stmt.where(
            PlanTrackingRecord.department.in_(actor.scope.department_names)
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


@router.get("/my-todos", response_model=BusinessTodoPage, summary="本人人事待办")
async def hr_my_todos(
    request: Request,
    user: RequiredUser,
    kind: Literal["plan-tracking", "position-transfer"],
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> BusinessTodoPage:
    if current_page_key.get() != PAGES[kind]:
        raise HTTPException(403, "当前页面不能读取其他人事业务的待办")
    actor = await resolve_todo_actor(request, db, user)
    if kind == "position-transfer":
        if not actor.can_approve:
            raise HTTPException(403, "未授权审批岗位调动待办")
        records, total = await PositionTransferRecordService(db).list_approvals(
            current_user=user,
            tab="pending_approval",
            page=page,
            page_size=page_size,
            dept_alias_set=None if actor.scope.is_all else actor.scope.department_names,
            allow_name_fallback=actor.unique_name is not None,
        )
        return BusinessTodoPage(
            items=[
                BusinessTodoItem(
                    id=str(record.id),
                    title=f"{record.employee_name} · 岗位调动",
                    detail=record.apply_position or "待本人审批",
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    return await list_hr_todos(db, actor, page, page_size)
