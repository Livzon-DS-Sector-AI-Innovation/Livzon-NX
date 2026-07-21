"""Persistence helpers for platform-owned external quality records."""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelClass = type[Any]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def create_record(
    db: AsyncSession, model: ModelClass, data: dict[str, Any]
) -> Any:
    record = model(**data)
    db.add(record)
    await db.flush()
    return record


async def get_record_by_id(
    db: AsyncSession,
    model: ModelClass,
    record_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> Any | None:
    query = select(model).where(model.id == record_id)
    if not include_deleted:
        query = query.where(model.is_deleted.is_(False))
    return (await db.execute(query)).scalar_one_or_none()


async def get_record_by_value(
    db: AsyncSession,
    model: ModelClass,
    *,
    field_name: str,
    value: str,
    exclude_id: uuid.UUID | None = None,
) -> Any | None:
    query = select(model).where(getattr(model, field_name) == value)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    return (await db.execute(query)).scalar_one_or_none()


async def list_records(
    db: AsyncSession,
    model: ModelClass,
    *,
    search_fields: tuple[str, ...],
    filters: dict[str, Any],
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    conditions = [model.is_deleted.is_(False)]
    for field_name, value in filters.items():
        if value is not None:
            conditions.append(getattr(model, field_name) == value)
    if keyword and keyword.strip():
        pattern = f"%{_escape_like(keyword.strip())}%"
        conditions.append(
            or_(
                *[
                    getattr(model, field_name).ilike(pattern, escape="\\")
                    for field_name in search_fields
                ]
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(model).where(*conditions))
    ).scalar_one()
    rows = await db.execute(
        select(model)
        .where(*conditions)
        .order_by(model.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.scalars().all()), total


async def list_records_by_value(
    db: AsyncSession,
    model: ModelClass,
    *,
    field_name: str,
    value: Any,
    order_field: str = "created_at",
) -> list[Any]:
    rows = await db.execute(
        select(model)
        .where(getattr(model, field_name) == value, model.is_deleted.is_(False))
        .order_by(getattr(model, order_field).asc(), model.created_at.asc())
    )
    return list(rows.scalars().all())


async def update_record(db: AsyncSession, record: Any, data: dict[str, Any]) -> None:
    for field_name, value in data.items():
        setattr(record, field_name, value)
    await db.flush()


async def soft_delete_record(db: AsyncSession, record: Any) -> None:
    record.is_deleted = True
    await db.flush()
