"""Resolve browser hints against the current user's live page grants."""

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGE_DEFINITIONS

from .schemas import AgentPageContext

FILTER_KEYS = frozenset(
    {
        "keyword",
        "status",
        "page",
        "page_size",
        "date_from",
        "date_to",
        "department_id",
        "product_id",
        "year",
        "month",
    }
)


async def resolve_page_context(
    db: AsyncSession,
    *,
    user: User,
    hint: object,
) -> AgentPageContext | None:
    if not isinstance(hint, Mapping):
        return None
    route = hint.get("route_path")
    if not isinstance(route, str) or len(route) > 300:
        return None
    # Exact registered routes only: do not turn arbitrary URLs into authority.
    candidates = [item for item in PAGE_DEFINITIONS if item.route_path == route]
    page = candidates[0] if len(candidates) == 1 else None
    if (
        page is None
        or page.page_key.startswith("system:")
        or page.route_path.startswith("/settings")
    ):
        return None
    grants = await PagePermissionService().effective_grants(db, user=user)
    if not any(
        grant.page_key == page.page_key and "query" in grant.permissions
        for grant in grants
    ):
        return None
    raw_filters = hint.get("filters")
    filters = (
        {
            key: value
            for key, value in raw_filters.items()
            if key in FILTER_KEYS and isinstance(value, str) and len(value) <= 200
        }
        if isinstance(raw_filters, Mapping)
        else {}
    )
    return AgentPageContext(
        page_key=page.page_key,
        page_name=page.page_name,
        module_code=page.module_code,
        route_path=page.route_path,
        filters=filters,
    )
