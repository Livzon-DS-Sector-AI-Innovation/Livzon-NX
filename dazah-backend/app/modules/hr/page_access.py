"""Reviewed employee-page scope; legacy HR policies remain unchanged in draft."""

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.hr.models import Employee
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_key,
    resolve_user_department_scope,
)

EMPLOYEE_PAGE_KEY = "hr:employee-management:profile"


async def employee_page_scope(db: AsyncSession) -> DepartmentScope | None:
    page_key = current_page_key.get()
    if page_key is None:
        return None
    if page_key != EMPLOYEE_PAGE_KEY:
        raise HTTPException(403, "当前页面未登记员工档案访问能力")
    actor = current_page_actor.get()
    if actor is None:
        raise HTTPException(403, "页面授权缺少可信用户身份")
    scope = await resolve_user_department_scope(db, actor)
    if not scope.is_all and not scope.department_names:
        raise HTTPException(403, "当前员工页面没有可访问的部门范围")
    return scope


def employee_department_expression() -> ColumnElement[str]:
    """The most specific recorded department owns the employee, never an OR."""
    return func.coalesce(
        func.nullif(func.trim(Employee.sub_department), ""),
        func.trim(Employee.department),
    )


def assert_employee_department(
    scope: DepartmentScope | None, department: str | None, sub_department: str | None
) -> None:
    owner = (sub_department or "").strip() or (department or "").strip()
    if scope is not None and not scope.allows(owner):
        raise HTTPException(403, "员工档案不在当前页面授权的部门范围内")


def assert_employee_filter(scope: DepartmentScope, department: str | None) -> None:
    if department is not None and not scope.allows(department.strip()):
        raise HTTPException(403, "无权查询指定部门的员工档案")
