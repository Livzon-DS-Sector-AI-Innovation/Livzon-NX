"""Purchase-request page scope, shared by HTTP and the trusted tool executor."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_key,
    resolve_user_department_scope,
)
from app.platform.identity.page_policy import get_page_definition


def request_page_category() -> str | None:
    key = current_page_key.get()
    if key is None:
        return None  # Legacy module: existing policy remains unchanged.
    page = get_page_definition(key)
    if page is None or page.module_code != "procurement":
        raise HTTPException(403, "当前页面不能访问采购申请")
    parts = page.route_path.strip("/").split("/")
    if page.route_path == "/purchasing/order":
        return None
    if len(parts) < 3 or parts[1] not in {"request", "approval"}:
        raise HTTPException(403, "当前页面不能访问采购申请")
    return parts[2]


def constrain_request_category(requested: str | None) -> str | None:
    category = request_page_category()
    if category is not None and requested is not None and category != requested:
        raise HTTPException(403, "不能跨菜单页面访问其他采购类型")
    return category or requested


async def request_department_names(db: AsyncSession) -> set[str] | None:
    actor = current_page_actor.get()
    if actor is None:
        if current_page_key.get() is not None:
            raise HTTPException(403, "页面授权缺少可信用户身份")
        return None
    scope = await resolve_user_department_scope(db, actor)
    if scope.is_all:
        return None
    if not scope.department_names:
        raise HTTPException(403, "当前页面没有可访问的部门范围")
    return scope.department_names


async def assert_request_scope(
    db: AsyncSession, *, category: str, department: str
) -> None:
    constrain_request_category(category)
    departments = await request_department_names(db)
    if departments is not None and department not in departments:
        raise HTTPException(403, "采购申请不在当前页面授权的部门范围内")


def assert_approval_responsibility(approval_role: str, approver_name: str) -> str:
    key = current_page_key.get()
    if key is None:
        actor = current_page_actor.get()
        if actor is not None and actor.role == "admin":
            return actor.name
        return approver_name
    page = get_page_definition(key)
    actor = current_page_actor.get()
    if page is None or actor is None or "/approval/" not in page.route_path:
        raise HTTPException(403, "当前页面不具备采购审批职责")
    role = page.route_path.rsplit("/", 1)[-1].replace("-", "_")
    if role != approval_role:
        raise HTTPException(403, "不能代替其他审批岗位作出责任判断")
    # Identity comes from the authenticated account, not a caller-supplied name.
    return actor.name


def constrain_contract_category(requested: str | None = None) -> str | None:
    key = current_page_key.get()
    if key is None:
        return requested
    page = get_page_definition(key)
    if page is None:
        raise HTTPException(403, "合同页面授权无效")
    if page.route_path == "/purchasing/contract-summary":
        return requested
    if not page.route_path.startswith("/purchasing/contract-generation/"):
        raise HTTPException(403, "当前页面不能访问采购合同")
    category = page.route_path.rsplit("/", 1)[-1]
    if requested is not None and requested != category:
        raise HTTPException(403, "不能跨页面查看或生成其他类别的合同")
    return category
