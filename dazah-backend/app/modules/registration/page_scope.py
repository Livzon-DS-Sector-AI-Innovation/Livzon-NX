"""Sheet ownership for shared registration workbook endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.platform.identity.data_scope import current_page_actor, current_page_key
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGES_BY_MODULE

WorkbookFamily = Literal[
    "project-ledger", "declaration-progress", "certificate-management"
]
PREFIXES: dict[WorkbookFamily, str] = {
    "project-ledger": "registration:project:project-ledger:",
    "declaration-progress": "registration:project:declaration-progress:",
    "certificate-management": "registration:certificate-management:",
}
_workbook_scope: ContextVar[WorkbookFamily | None] = ContextVar(
    "registration_workbook_scope", default=None
)


def family_sheet_keys(family: WorkbookFamily) -> frozenset[str]:
    prefix = PREFIXES[family]
    return frozenset(
        page.page_key.removeprefix(prefix)
        for page in PAGES_BY_MODULE["registration"]
        if page.page_key.startswith(prefix)
    )


async def visible_sheet_keys(
    session: AsyncSession, family: WorkbookFamily
) -> frozenset[str]:
    actor, page = current_page_actor.get(), current_page_key.get()
    all_keys = family_sheet_keys(family)
    if (actor is None and page is None) or (
        actor is not None and actor.role == "admin"
    ):
        return all_keys
    if actor is None or page is None:
        return frozenset()
    if _workbook_scope.get() == family:
        return all_keys
    prefix = PREFIXES[family]
    if page.startswith(prefix):
        return frozenset({page.removeprefix(prefix)}) & all_keys
    # Aggregated project dashboards may only summarize separately granted sheets.
    grants = await PagePermissionService().effective_grants(session, user=actor)
    return (
        frozenset(
            grant.page_key.removeprefix(prefix)
            for grant in grants
            if grant.page_key.startswith(prefix) and "query" in grant.permissions
        )
        & all_keys
    )


async def authorize_sheet(
    session: AsyncSession, family: WorkbookFamily, sheet_key: str
) -> None:
    if sheet_key not in await visible_sheet_keys(session, family):
        raise ForbiddenException("当前页面无权访问该台账子表")


@asynccontextmanager
async def authorized_workbook(
    session: AsyncSession,
    family: WorkbookFamily,
    action: Literal["bulk_import", "sensitive_export"],
) -> AsyncIterator[None]:
    """Whole-file replacement/export requires authority over every affected sheet."""
    actor, page = current_page_actor.get(), current_page_key.get()
    trusted = (actor is None and page is None) or (
        actor is not None and actor.role == "admin"
    )
    if not trusted:
        if actor is None:
            raise ForbiddenException("无法确认工作簿操作权限")
        prefix = PREFIXES[family]
        grants = await PagePermissionService().effective_grants(session, user=actor)
        authorized = {
            grant.page_key.removeprefix(prefix)
            for grant in grants
            if grant.page_key.startswith(prefix)
            and "operate" in grant.permissions
            and action in grant.sensitive_actions
        }
        if not family_sheet_keys(family).issubset(authorized):
            raise ForbiddenException("整本导入或导出需要所有子表的对应操作权限")
    token = _workbook_scope.set(family)
    try:
        yield
    finally:
        _workbook_scope.reset(token)
