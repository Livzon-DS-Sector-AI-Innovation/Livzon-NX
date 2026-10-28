"""Personal hazard rectification and inspection work."""

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
from app.modules.safety.models import Accident, HazardReport, SafetyCheck
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequiredUser
from app.platform.identity.todo_access import (
    TodoActor,
    resolve_todo_actor,
    todo_led_departments,
)
from app.shared.todo_schemas import BusinessTodoItem, BusinessTodoPage

SafetyTodoKind = Literal["hazards", "accidents", "checks"]
PAGES = {
    "hazards": "safety:risk-hazard:hazard-inspection:hazard-inspection-ledger",
    "accidents": "safety:emergency-accident:accident-ledger",
    "checks": "safety:training-check:safety-check",
}
router = APIRouter()


def safety_todo_query(
    kind: SafetyTodoKind, actor: TodoActor, led_departments: set[str]
) -> Select[tuple[str, str, str, date | None]]:
    name = actor.unique_name
    if kind == "hazards":
        rectifier = or_(
            HazardReport.rectification_responsible_person == actor.user_id,
            and_(
                HazardReport.rectification_responsible_person.is_(None),
                HazardReport.rectification_responsible_person_name == name
                if name
                else false(),
            ),
        )
        rectify = and_(
            rectifier,
            HazardReport.rectification_status.in_(
                ["pending", "in_progress", "rejected"]
            ),
        )
        verify_first = (
            and_(
                HazardReport.department.in_(led_departments),
                HazardReport.rectification_status == "replied",
                HazardReport.verify_level_1_status == "pending",
            )
            if actor.can_approve
            else false()
        )
        discoverer = or_(
            HazardReport.discovered_by == actor.user_id,
            and_(
                HazardReport.discovered_by.is_(None),
                HazardReport.discovered_by_name == name if name else false(),
            ),
        )
        verify_last = (
            and_(
                discoverer,
                HazardReport.rectification_status == "level2_approved",
                HazardReport.verify_level_3_status == "pending",
            )
            if actor.can_approve
            else false()
        )
        stmt = select(
            cast(HazardReport.id, String).label("id"),
            func.concat(HazardReport.hazard_no, " · ", HazardReport.description).label(
                "title"
            ),
            case(
                (rectify, "待整改／重新整改"),
                (verify_first, "待部门负责人复核"),
                else_="待检查人员复核",
            ).label("detail"),
            cast(func.timezone("Asia/Shanghai", HazardReport.deadline), Date).label(
                "due_date"
            ),
        ).where(
            HazardReport.is_deleted.is_(False),
            HazardReport.status != "closed",
            or_(rectify, verify_first, verify_last),
        )
        department = HazardReport.department
    elif kind == "accidents":
        stmt = select(
            cast(Accident.id, String).label("id"),
            func.concat(Accident.accident_no, " · ", Accident.description).label(
                "title"
            ),
            literal("待完成事故纠正预防措施").label("detail"),
            cast(
                func.timezone("Asia/Shanghai", Accident.corrective_action_deadline),
                Date,
            ).label("due_date"),
        ).where(
            Accident.is_deleted.is_(False),
            Accident.status != "closed",
            Accident.corrective_action_status.in_(["pending", "in_progress"]),
            Accident.corrective_action_responsible == name if name else false(),
        )
        department = Accident.department
    elif kind == "checks":
        inspector = or_(
            SafetyCheck.inspector == actor.user_id,
            and_(
                SafetyCheck.inspector.is_(None),
                SafetyCheck.inspector_name == name if name else false(),
            ),
        )
        stmt = select(
            cast(SafetyCheck.id, String).label("id"),
            func.concat(SafetyCheck.check_no, " · 安全检查").label("title"),
            literal("待完善并提交检查记录").label("detail"),
            cast(func.timezone("Asia/Shanghai", SafetyCheck.check_date), Date).label(
                "due_date"
            ),
        ).where(
            SafetyCheck.is_deleted.is_(False), SafetyCheck.status == "draft", inspector
        )
        department = SafetyCheck.department
    if not actor.scope.is_all:
        stmt = stmt.where(department.in_(actor.scope.department_names))
    return stmt


async def list_safety_todos(
    db: AsyncSession, kind: SafetyTodoKind, actor: TodoActor, page: int, page_size: int
) -> BusinessTodoPage:
    led = (
        await todo_led_departments(db, actor)
        if kind == "hazards" and actor.can_approve
        else set()
    )
    stmt = safety_todo_query(kind, actor, led)
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


@router.get("/my-todos", response_model=BusinessTodoPage, summary="本人安全待办")
async def safety_my_todos(
    request: Request,
    user: RequiredUser,
    kind: SafetyTodoKind,
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> BusinessTodoPage:
    if current_page_key.get() != PAGES[kind]:
        raise HTTPException(403, "当前页面不能读取其他安全业务的待办")
    actor = await resolve_todo_actor(request, db, user)
    return await list_safety_todos(db, kind, actor, page, page_size)
