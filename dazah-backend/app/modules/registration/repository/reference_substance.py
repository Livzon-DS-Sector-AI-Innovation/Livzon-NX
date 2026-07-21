"""Reference substance database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models.reference_substance import ReferenceSubstance


async def create_reference_substance(
    db: AsyncSession, data: dict[str, Any]
) -> ReferenceSubstance:
    """创建对照品记录"""
    substance = ReferenceSubstance(**data)
    db.add(substance)
    await db.flush()
    return substance


async def get_reference_substances(db: AsyncSession) -> list[ReferenceSubstance]:
    """获取所有对照品记录"""
    query = (
        select(ReferenceSubstance)
        .where(ReferenceSubstance.is_deleted == False)  # noqa: E712
        .order_by(ReferenceSubstance.created_at.desc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_reference_substance_by_id(
    db: AsyncSession, substance_id: uuid.UUID
) -> ReferenceSubstance | None:
    """根据ID获取对照品记录"""
    query = (
        select(ReferenceSubstance)
        .where(
            ReferenceSubstance.id == substance_id,
            ReferenceSubstance.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_reference_substance(
    db: AsyncSession,
    substance_id: uuid.UUID,
    data: dict[str, Any],
) -> ReferenceSubstance | None:
    """更新对照品记录"""
    substance = await get_reference_substance_by_id(db, substance_id)
    if not substance:
        return None
    for key, value in data.items():
        if hasattr(substance, key):
            setattr(substance, key, value)
    await db.flush()
    return substance


async def delete_reference_substance(
    db: AsyncSession, substance_id: uuid.UUID
) -> bool:
    """软删除对照品记录"""
    substance = await get_reference_substance_by_id(db, substance_id)
    if not substance:
        return False
    substance.is_deleted = True
    await db.flush()
    return True
