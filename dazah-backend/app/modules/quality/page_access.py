"""Reviewed local deviation-ledger scope; draft modules keep legacy behavior."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
    resolve_user_department_scope,
)

DEVIATION_LEDGER_PAGE = "quality:deviations:deviation-ledger"


async def deviation_page_scope(db: AsyncSession) -> DepartmentScope | None:
    page_key = current_page_key.get()
    if page_key is None:
        return None
    if page_key != DEVIATION_LEDGER_PAGE:
        raise HTTPException(403, "当前页面未登记偏差台账访问能力")
    actor = current_page_actor.get()
    if actor is None:
        raise HTTPException(403, "页面授权缺少可信用户身份")
    configured = current_page_data_scope.get()
    if getattr(actor, "role", None) != "admin" and (
        configured is None
        or configured.get("scope_type") not in {"all", "departments", "department_tree"}
    ):
        raise HTTPException(403, "偏差台账缺少有效页面数据范围")
    scope = await resolve_user_department_scope(db, actor)
    if not scope.is_all and not scope.department_names:
        raise HTTPException(403, "当前偏差台账没有可访问的部门范围")
    return scope


def assert_deviation_department(
    scope: DepartmentScope | None, department: str | None
) -> None:
    if scope is not None and not scope.allows(department):
        raise HTTPException(403, "偏差记录不在当前页面授权的部门范围内")
