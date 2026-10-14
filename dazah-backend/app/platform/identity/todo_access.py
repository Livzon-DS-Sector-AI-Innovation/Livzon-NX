"""Trusted identity and page scope for personal business task previews."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
    resolve_user_department_scope,
)
from app.platform.identity.models import Department, User


@dataclass(frozen=True)
class TodoActor:
    user_id: UUID
    unique_name: str | None
    person_ids: tuple[str, ...]
    scope: DepartmentScope
    can_approve: bool = False


async def resolve_todo_actor(
    request: Request, db: AsyncSession, user: User
) -> TodoActor:
    actor = current_page_actor.get()
    configured = current_page_data_scope.get()
    if (
        actor is None
        or actor.id != user.id
        or not current_page_key.get()
        or configured is None
    ):
        raise HTTPException(403, "待办请求缺少可信页面权限和数据范围")
    grant = getattr(request.state, "page_permission", None)
    if user.role != "admin" and (
        grant is None or not {"access", "query", "operate"}.issubset(grant.permissions)
    ):
        raise HTTPException(403, "当前页面未授权处理待办事项")
    scope_type = configured.get("scope_type")
    if scope_type == "not_applicable":
        # Older equipment/safety grants predate department-scoped APIs. Keep
        # their identity/role department policy rather than turning this value
        # into unrestricted reads for a newly reviewed task endpoint.
        token = current_page_data_scope.set(None)
        try:
            scope = await resolve_user_department_scope(db, user)
        finally:
            current_page_data_scope.reset(token)
    elif scope_type in {"all", "departments", "department_tree"}:
        scope = await resolve_user_department_scope(db, user)
    else:
        raise HTTPException(403, "当前待办数据范围尚不支持，请联系管理员调整页面授权")
    name = (user.name or "").strip()
    # Legacy name-only assignments cannot safely distinguish namesakes. Stable
    # IDs always take precedence; ambiguous names never generate personal tasks.
    count = (
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                func.trim(User.name) == name
            )
        )
        if name
        else 0
    )
    return TodoActor(
        user_id=user.id,
        unique_name=name if count == 1 else None,
        person_ids=tuple(
            dict.fromkeys(
                value
                for value in (
                    str(user.id),
                    user.feishu_open_id,
                    user.feishu_user_id,
                    user.feishu_union_id,
                )
                if value
            )
        ),
        scope=scope,
        can_approve=user.role == "admin"
        or (grant is not None and "approve" in grant.sensitive_actions),
    )


async def todo_department_ids(
    db: AsyncSession, scope: DepartmentScope
) -> set[UUID] | None:
    if scope.is_all:
        return None
    result = await db.scalars(
        select(Department.id).where(
            Department.name.in_(scope.department_names),
            Department.name.in_(
                select(Department.name)
                .where(
                    Department.is_deleted.is_(False),
                    Department.status_is_deleted.is_not(True),
                )
                .group_by(Department.name)
                .having(func.count() == 1)
            ),
            Department.is_deleted.is_(False),
            Department.status_is_deleted.is_not(True),
        )
    )
    return set(result)


async def todo_led_departments(db: AsyncSession, actor: TodoActor) -> set[str]:
    result = await db.scalars(
        select(Department.name).where(
            Department.leader_user_id.in_(actor.person_ids),
            Department.name.in_(
                select(Department.name)
                .where(
                    Department.is_deleted.is_(False),
                    Department.status_is_deleted.is_not(True),
                )
                .group_by(Department.name)
                .having(func.count() == 1)
            ),
            Department.is_deleted.is_(False),
            Department.status_is_deleted.is_not(True),
        )
    )
    return set(result)
