"""Resolve workshop ownership from authenticated page grants, never display labels."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.platform.identity.data_scope import current_page_actor, current_page_key
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGES_BY_MODULE

WORKSHOP_PAGE_PREFIX = "production:batches:workshop-"
WORKSHOP_CODES = frozenset(
    page.page_key.removeprefix(WORKSHOP_PAGE_PREFIX).split(":", 1)[0]
    for page in PAGES_BY_MODULE["production"]
    if page.page_key.startswith(WORKSHOP_PAGE_PREFIX)
)


async def allowed_batch_workshops(
    session: AsyncSession, *, write: bool = False
) -> frozenset[str] | None:
    """None means unrestricted; an empty set means no workshop is authorized."""
    actor = current_page_actor.get()
    page = current_page_key.get()
    if actor is None and page is None:
        # Trusted background jobs have no HTTP page context.
        return None
    if actor is not None and actor.role == "admin":
        return None
    if actor is None or page is None:
        return frozenset()
    if page.startswith(WORKSHOP_PAGE_PREFIX):
        code = page.removeprefix(WORKSHOP_PAGE_PREFIX).split(":", 1)[0]
        return frozenset({code}) if code in WORKSHOP_CODES else frozenset()
    if page == "production:overview" and not write:
        return None
    if page not in {"production:overview", "production:records", "production:balance"}:
        return frozenset()
    required = "operate" if write else "query"
    grants = await PagePermissionService().effective_grants(session, user=actor)
    return frozenset(
        grant.page_key.removeprefix(WORKSHOP_PAGE_PREFIX).split(":", 1)[0]
        for grant in grants
        if grant.page_key.startswith(WORKSHOP_PAGE_PREFIX)
        and grant.page_key.removeprefix(WORKSHOP_PAGE_PREFIX).split(":", 1)[0]
        in WORKSHOP_CODES
        and required in grant.permissions
    )


async def authorize_batch_workshop(
    session: AsyncSession, code: str | None, *, assign_current: bool = False
) -> str | None:
    """Validate the target of a create or ownership change before persistence."""
    allowed = await allowed_batch_workshops(session, write=True)
    page = current_page_key.get() or ""
    if code is None and assign_current and page.startswith(WORKSHOP_PAGE_PREFIX):
        code = page.removeprefix(WORKSHOP_PAGE_PREFIX).split(":", 1)[0]
    if code is not None and code not in WORKSHOP_CODES:
        raise ForbiddenException("所属车间无效")
    if allowed is not None and code not in allowed:
        raise ForbiddenException("没有操作该车间批次的权限")
    return code
