"""Personal quality work, using the same record owners as quality ledgers."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import (
    Date,
    Select,
    String,
    and_,
    case,
    cast,
    false,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.quality.models import (
    CAPA,
    CapaPlanTrack,
    ChangeActionPlan,
    ChangeControl,
    Deviation,
)
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import TodoActor, resolve_todo_actor
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

QualityTodoKind = Literal["deviations", "capas", "capa-plans", "change-plans"]
PAGES = {
    "deviations": "quality:deviations:deviation-ledger",
    "capas": "quality:capas:capa-ledger",
    "capa-plans": "quality:capas:capa-plans",
    "change-plans": "quality:change:change-action-plans",
}
router = APIRouter()


def quality_todo_query(
    kind: QualityTodoKind, actor: TodoActor
) -> Select[tuple[str, str, str, date | None]]:
    name = actor.unique_name
    if kind == "deviations":
        personal = or_(
            and_(
                Deviation.status.in_(["draft", "returned"]),
                or_(
                    Deviation.reporter_id == actor.user_id,
                    Deviation.created_by == actor.user_id,
                ),
            ),
            and_(
                Deviation.status == "pending_investigation",
                Deviation.handler == name if name else false(),
            ),
        )
        stmt = select(
            cast(Deviation.id, String).label("id"),
            func.concat(Deviation.deviation_code, " · ", Deviation.title).label(
                "title"
            ),
            case(
                (Deviation.status == "pending_investigation", "待调查"),
                (Deviation.status == "returned", "已退回，待补充"),
                else_="待完善并提交",
            ).label("detail"),
            literal(None, type_=Date).label("due_date"),
        ).where(Deviation.is_deleted.is_(False), personal)
        department = Deviation.department
    elif kind == "capas":
        personal = or_(
            and_(
                CAPA.status.in_(["draft", "returned"]), CAPA.created_by == actor.user_id
            ),
            and_(
                CAPA.status == "executing",
                CAPA.executors.contains([name]) if name else false(),
            ),
        )
        stmt = select(
            cast(CAPA.id, String).label("id"),
            func.concat(CAPA.capa_code, " · ", func.coalesce(CAPA.title, "CAPA")).label(
                "title"
            ),
            case(
                (CAPA.status == "executing", "待执行"),
                (CAPA.status == "returned", "已退回，待补充"),
                else_="待完善并提交",
            ).label("detail"),
            cast(
                func.timezone("Asia/Shanghai", CAPA.expected_completion_date), Date
            ).label("due_date"),
        ).where(CAPA.is_deleted.is_(False), personal)
        department = CAPA.department
    elif kind == "capa-plans":
        owner = and_(
            CapaPlanTrack.owner_name == name if name else false(),
            or_(
                CapaPlanTrack.owner_confirmed.is_(False),
                func.coalesce(CapaPlanTrack.progress, "").not_in(
                    ["已完成", "已关闭", "完成", "completed", "closed", "100%", "100"]
                ),
            ),
        )
        confirm = (
            and_(
                CapaPlanTrack.department_head == name if name else false(),
                CapaPlanTrack.owner_confirmed.is_(True),
                CapaPlanTrack.department_head_confirmed.is_(False),
            )
            if actor.can_approve
            else false()
        )
        stmt = (
            select(
                cast(CapaPlanTrack.id, String).label("id"),
                func.concat(
                    CapaPlanTrack.capa_code, " · ", CapaPlanTrack.plan_content
                ).label("title"),
                case((owner, "待完成计划"), else_="待部门负责人确认").label("detail"),
                CapaPlanTrack.due_date.label("due_date"),
            )
            .join(CAPA, CapaPlanTrack.capa_id == CAPA.id)
            .where(
                CapaPlanTrack.is_deleted.is_(False),
                CAPA.is_deleted.is_(False),
                CAPA.status.not_in(["closed", "cancelled"]),
                or_(owner, confirm),
            )
        )
        department = CAPA.department
    else:
        # IDs may be local or Feishu IDs. A populated ID belonging to someone
        # else must never fall back to a coincidentally matching display name.
        owner = or_(
            ChangeActionPlan.owner_user_id.in_(actor.person_ids),
            and_(
                or_(
                    ChangeActionPlan.owner_user_id.is_(None),
                    ChangeActionPlan.owner_user_id == "",
                ),
                ChangeActionPlan.owner_name == name if name else false(),
            ),
        )
        stmt = (
            select(
                cast(ChangeActionPlan.id, String).label("id"),
                func.concat(
                    ChangeActionPlan.change_code, " · ", ChangeActionPlan.project_name
                ).label("title"),
                literal("待完成变更计划").label("detail"),
                func.coalesce(
                    ChangeActionPlan.delayed_deadline_date,
                    ChangeActionPlan.deadline_date,
                ).label("due_date"),
            )
            .join(
                ChangeControl, ChangeActionPlan.change_code == ChangeControl.change_code
            )
            .where(
                ChangeActionPlan.is_deleted.is_(False),
                ChangeControl.is_deleted.is_(False),
                ChangeControl.closure_date.is_(None),
                func.coalesce(ChangeActionPlan.status, "").not_in(
                    ["已完成", "已关闭", "已确认"]
                ),
                owner,
            )
        )
        department = ChangeControl.applicant_department
    if not actor.scope.is_all:
        stmt = stmt.where(department.in_(actor.scope.department_names))
    return stmt


async def list_quality_todos(
    db: AsyncSession, kind: QualityTodoKind, actor: TodoActor, page: int, page_size: int
) -> BusinessTodoPage:
    stmt = quality_todo_query(kind, actor)
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


@router.get("/my-todos", response_model=BusinessTodoPage, summary="本人质量待办")
async def quality_my_todos(
    request: Request,
    user: RequiredUser,
    kind: QualityTodoKind,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> BusinessTodoPage:
    if current_page_key.get() != PAGES[kind]:
        raise HTTPException(403, "当前页面不能读取其他质量业务的待办")
    actor = await resolve_todo_actor(request, db, user)
    return await list_quality_todos(db, kind, actor, page, page_size)
