"""Department scope for safety ledgers with a recorded owning department."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
    resolve_user_department_scope,
)

_DEPARTMENT_LEDGER_PAGES = frozenset(
    {
        "safety:emergency-accident:accident-ledger",
        "safety:risk-hazard:hazard-inspection:hazard-inspection-ledger",
        "safety:training-check:safety-check",
    }
)


async def ledger_department_scope(db: AsyncSession) -> DepartmentScope:
    if current_page_key.get() not in _DEPARTMENT_LEDGER_PAGES:
        return DepartmentScope(is_all=True)
    actor = current_page_actor.get()
    if actor is None or current_page_data_scope.get() is None:
        raise ForbiddenException("无法确定当前安全台账的数据范围")
    return await resolve_user_department_scope(db, actor)


def require_ledger_department(scope: DepartmentScope, department: str | None) -> None:
    if not scope.allows(department):
        raise ForbiddenException("当前页面无权访问该部门的数据")


def reject_direct_workflow_edit(data: BaseModel, *fields: str) -> None:
    actor = current_page_actor.get()
    if (
        current_page_key.get() is not None
        and getattr(actor, "role", None) != "admin"
        and data.model_fields_set.intersection(fields)
    ):
        raise ForbiddenException("流程状态必须通过对应业务操作变更")
