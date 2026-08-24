"""Persistence helpers for OOS/OOT records and OOT limit definitions."""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.oos_oot import OosOotRecord
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def create_oos_oot_record(db: AsyncSession, data: dict[str, Any]) -> OosOotRecord:
    record = OosOotRecord(**data)
    db.add(record)
    await db.flush()
    return record


async def get_oos_oot_record(
    db: AsyncSession, record_id: uuid.UUID, *, include_deleted: bool = False
) -> OosOotRecord | None:
    query = select(OosOotRecord).where(OosOotRecord.id == record_id)
    if not include_deleted:
        query = query.where(OosOotRecord.is_deleted.is_(False))
    return (await db.execute(query)).scalar_one_or_none()


async def get_oos_oot_record_by_code(
    db: AsyncSession, record_code: str, *, exclude_id: uuid.UUID | None = None
) -> OosOotRecord | None:
    query = select(OosOotRecord).where(OosOotRecord.record_code == record_code)
    if exclude_id is not None:
        query = query.where(OosOotRecord.id != exclude_id)
    return (await db.execute(query)).scalar_one_or_none()


async def list_oos_oot_records(
    db: AsyncSession,
    *,
    record_type: str | None,
    status: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[OosOotRecord], int]:
    conditions: list[ColumnElement[bool]] = [OosOotRecord.is_deleted.is_(False)]
    if record_type:
        conditions.append(OosOotRecord.record_type == record_type)
    if status:
        conditions.append(OosOotRecord.status == status)
    if keyword and keyword.strip():
        pattern = f"%{_escape_like(keyword.strip())}%"
        conditions.append(
            or_(
                OosOotRecord.record_code.ilike(pattern, escape="\\"),
                OosOotRecord.title.ilike(pattern, escape="\\"),
                OosOotRecord.product_name.ilike(pattern, escape="\\"),
                OosOotRecord.batch_number.ilike(pattern, escape="\\"),
                OosOotRecord.test_item.ilike(pattern, escape="\\"),
            )
        )
    total = (
        await db.execute(
            select(func.count()).select_from(OosOotRecord).where(*conditions)
        )
    ).scalar_one()
    rows = await db.execute(
        select(OosOotRecord)
        .where(*conditions)
        .order_by(OosOotRecord.discovery_date.desc(), OosOotRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.scalars().all()), total


async def update_oos_oot_record(
    db: AsyncSession, record: OosOotRecord, data: dict[str, Any]
) -> OosOotRecord:
    for field_name, value in data.items():
        setattr(record, field_name, value)
    await db.flush()
    return await get_oos_oot_record(db, record.id) or record


async def soft_delete_oos_oot_record(db: AsyncSession, record: OosOotRecord) -> None:
    record.is_deleted = True
    await db.flush()
    await get_oos_oot_record(db, record.id, include_deleted=True)


async def create_oot_limit_product(
    db: AsyncSession, data: dict[str, Any]
) -> OotLimitProduct:
    normalized = dict(data)
    normalized.setdefault("document_no", normalized.get("document_title") or None)
    normalized.setdefault("document_version", normalized.get("version_label"))
    product = OotLimitProduct(**normalized)
    db.add(product)
    await db.flush()
    return product


async def get_oot_limit_product(
    db: AsyncSession, product_id: uuid.UUID, *, include_deleted: bool = False
) -> OotLimitProduct | None:
    query = select(OotLimitProduct).where(OotLimitProduct.id == product_id)
    if not include_deleted:
        query = query.where(OotLimitProduct.is_deleted.is_(False))
    return (await db.execute(query)).scalar_one_or_none()


async def get_oot_limit_product_by_code(
    db: AsyncSession, product_code: str, *, exclude_id: uuid.UUID | None = None
) -> OotLimitProduct | None:
    query = select(OotLimitProduct).where(OotLimitProduct.product_code == product_code)
    if exclude_id is not None:
        query = query.where(OotLimitProduct.id != exclude_id)
    return (await db.execute(query)).scalar_one_or_none()


async def list_oot_limit_products(
    db: AsyncSession, *, keyword: str | None
) -> list[OotLimitProduct]:
    conditions: list[ColumnElement[bool]] = [OotLimitProduct.is_deleted.is_(False)]
    if keyword and keyword.strip():
        pattern = f"%{_escape_like(keyword.strip())}%"
        conditions.append(
            or_(
                OotLimitProduct.product_code.ilike(pattern, escape="\\"),
                OotLimitProduct.product_name.ilike(pattern, escape="\\"),
                OotLimitProduct.document_no.ilike(pattern, escape="\\"),
            )
        )
    rows = await db.execute(
        select(OotLimitProduct)
        .where(*conditions)
        .order_by(OotLimitProduct.product_code.asc())
    )
    return list(rows.scalars().all())


async def update_oot_limit_product(
    db: AsyncSession, product: OotLimitProduct, data: dict[str, Any]
) -> OotLimitProduct:
    for field_name, value in data.items():
        setattr(product, field_name, value)
    await db.flush()
    return await get_oot_limit_product(db, product.id) or product


async def soft_delete_oot_limit_product(
    db: AsyncSession, product: OotLimitProduct
) -> None:
    product.is_deleted = True
    await db.flush()
    await get_oot_limit_product(db, product.id, include_deleted=True)


async def create_oot_limit_item(db: AsyncSession, data: dict[str, Any]) -> OotLimitItem:
    normalized = dict(data)
    normalized.setdefault("specification", normalized.get("standard_value") or "")
    normalized.setdefault("oot_limit", normalized.get("oot_limit_value") or "")
    item = OotLimitItem(**normalized)
    db.add(item)
    await db.flush()
    return item


async def get_oot_limit_item(
    db: AsyncSession, item_id: uuid.UUID, *, include_deleted: bool = False
) -> OotLimitItem | None:
    query = select(OotLimitItem).where(OotLimitItem.id == item_id)
    if not include_deleted:
        query = query.where(OotLimitItem.is_deleted.is_(False))
    return (await db.execute(query)).scalar_one_or_none()


async def get_oot_limit_item_by_order(
    db: AsyncSession,
    product_id: uuid.UUID,
    display_order: int,
    *,
    exclude_id: uuid.UUID | None = None,
) -> OotLimitItem | None:
    query = select(OotLimitItem).where(
        OotLimitItem.product_id == product_id,
        OotLimitItem.display_order == display_order,
        OotLimitItem.is_deleted.is_(False),
    )
    if exclude_id is not None:
        query = query.where(OotLimitItem.id != exclude_id)
    return (await db.execute(query)).scalar_one_or_none()


async def list_oot_limit_items(
    db: AsyncSession, product_id: uuid.UUID
) -> list[OotLimitItem]:
    rows = await db.execute(
        select(OotLimitItem)
        .where(
            OotLimitItem.product_id == product_id,
            OotLimitItem.is_deleted.is_(False),
        )
        .order_by(OotLimitItem.display_order.asc(), OotLimitItem.created_at.asc())
    )
    return list(rows.scalars().all())


async def update_oot_limit_item(
    db: AsyncSession, item: OotLimitItem, data: dict[str, Any]
) -> OotLimitItem:
    for field_name, value in data.items():
        setattr(item, field_name, value)
    await db.flush()
    return await get_oot_limit_item(db, item.id) or item


async def soft_delete_oot_limit_item(db: AsyncSession, item: OotLimitItem) -> None:
    item.is_deleted = True
    await db.flush()
    await get_oot_limit_item(db, item.id, include_deleted=True)
