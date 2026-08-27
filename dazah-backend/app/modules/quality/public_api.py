"""Quality module public API for cross-module access."""

from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.contacts import DepartmentContact

__all__ = [
    "DepartmentContact",
    "get_department_contact_by_open_id",
    "get_department_contact_list_from_feishu",
    "list_department_contacts",
]


async def list_department_contacts(
    session: AsyncSession,
) -> list[DepartmentContact]:
    """List active department contacts with open_id, ordered by department/name."""
    result = await session.execute(
        select(DepartmentContact)
        .where(
            DepartmentContact.is_deleted.is_(False),
            DepartmentContact.open_id.is_not(None),
        )
        .order_by(
            asc(DepartmentContact.department),
            asc(DepartmentContact.name),
            asc(DepartmentContact.created_at),
        )
    )
    return list(result.scalars().all())


async def get_department_contact_by_open_id(
    session: AsyncSession,
    open_id: str,
) -> DepartmentContact | None:
    """Get a department contact by open_id."""
    result = await session.execute(
        select(DepartmentContact).where(
            DepartmentContact.is_deleted.is_(False),
            DepartmentContact.open_id == open_id,
        )
    )
    return result.scalar_one_or_none()


async def get_department_contact_list_from_feishu(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 1000,
) -> Any:
    """Proxy to quality_management service for Feishu contact list."""
    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu as _impl,
    )

    return await _impl(session, page=page, page_size=page_size)
