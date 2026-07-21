"""Persistence helpers for quality inspection foundation records."""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelClass = type[Any]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def create_record(
    db: AsyncSession,
    model: ModelClass,
    data: dict[str, Any],
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

    count_query = select(func.count()).select_from(model).where(*conditions)
    total = (await db.execute(count_query)).scalar_one()
    records_query = (
        select(model)
        .where(*conditions)
        .order_by(model.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = list((await db.execute(records_query)).scalars().all())
    return records, total


async def exists_value(
    db: AsyncSession,
    model: ModelClass,
    *,
    field_name: str,
    value: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    conditions = [getattr(model, field_name) == value]
    if exclude_id is not None:
        conditions.append(model.id != exclude_id)
    query = select(model.id).where(*conditions).limit(1)
    return (await db.execute(query)).scalar_one_or_none() is not None


async def update_record(
    db: AsyncSession,
    record: Any,
    data: dict[str, Any],
) -> None:
    for field_name, value in data.items():
        setattr(record, field_name, value)
    await db.flush()


async def soft_delete_record(db: AsyncSession, record: Any) -> None:
    record.is_deleted = True
    await db.flush()
