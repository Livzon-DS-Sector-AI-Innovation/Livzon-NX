"""Material-page resource isolation shared by HTTP and trusted Agent calls."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_key,
    resolve_user_department_scope,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    WAREHOUSE_DEPARTMENT_DATA_PAGES,
    WAREHOUSE_MATERIAL_PAGE_ALIASES,
)


def assert_material_page(page_key: str) -> None:
    if page_key not in FEISHU_WAREHOUSE_MATERIAL_PAGES:
        raise HTTPException(404, "仓储飞书模板页不存在")
    authorized = current_page_key.get()
    if authorized is not None and (
        WAREHOUSE_MATERIAL_PAGE_ALIASES.get(authorized) != page_key
    ):
        raise HTTPException(403, "不能跨菜单页面访问其他仓储数据")


async def material_page_scope(
    db: AsyncSession, page_key: str, fallback: DepartmentScope | None = None
) -> DepartmentScope | None:
    assert_material_page(page_key)
    if current_page_key.get() is None:
        return fallback
    actor = current_page_actor.get()
    if actor is None:
        raise HTTPException(403, "页面授权缺少可信用户身份")
    if page_key not in WAREHOUSE_DEPARTMENT_DATA_PAGES:
        return None
    scope = await resolve_user_department_scope(db, actor)
    if not scope.is_all and not scope.department_names:
        raise HTTPException(403, "当前页面没有可访问的部门范围")
    return scope


def assert_record_department(scope: DepartmentScope | None, department: object) -> None:
    if scope is not None and not scope.is_all:
        # Do not stringify unknown rich objects or accept partially authorized arrays.
        if not isinstance(department, str) or not scope.allows(department.strip()):
            raise HTTPException(403, "仓储记录不在当前页面授权的部门范围内")


def assert_department_filters(
    scope: DepartmentScope | None, filters: list[dict[str, str]] | None
) -> None:
    for condition in filters or []:
        if condition.get("field") == "车间" and condition.get("operator") == "eq":
            assert_record_department(scope, condition.get("value"))


async def assert_material_refresh(db: AsyncSession) -> None:
    page_key = current_page_key.get()
    if page_key is None:
        return
    actor = current_page_actor.get()
    if actor is None:
        raise HTTPException(403, "页面授权缺少可信用户身份")
    grants = await PagePermissionService().effective_grants(db, user=actor)
    if not any(
        grant.page_key == page_key
        and "operate" in grant.permissions
        and "sync_config" in grant.sensitive_actions
        for grant in grants
    ):
        raise HTTPException(403, "未获得同步仓储页面数据授权")
