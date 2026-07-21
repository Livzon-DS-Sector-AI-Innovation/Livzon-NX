"""CPV Value database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.cpv_value import CpvValue


async def create_value(db: AsyncSession, data: dict[str, Any]) -> CpvValue:
    """创建参数值"""
    value = CpvValue(**data)
    db.add(value)
    await db.flush()
    return value


async def create_values_bulk(db: AsyncSession, data_list: list[dict[str, Any]]) -> list[CpvValue]:
    """批量创建参数值"""
    values = [CpvValue(**data) for data in data_list]
    db.add_all(values)
    await db.flush()
    return values


async def get_values_by_batch_id(db: AsyncSession, batch_id: uuid.UUID) -> list[CpvValue]:
    """根据批次ID获取参数值列表"""
    result = await db.execute(
        select(CpvValue).where(
            CpvValue.batch_id == batch_id,
            CpvValue.is_deleted == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def get_values_by_batch_ids(
    db: AsyncSession,
    batch_ids: list[uuid.UUID],
) -> list[CpvValue]:
    """根据批次ID列表获取参数值"""
    if not batch_ids:
        return []
    
    result = await db.execute(
        select(CpvValue).where(
            CpvValue.batch_id.in_(batch_ids),
            CpvValue.is_deleted == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def get_value(
    db: AsyncSession,
    batch_id: uuid.UUID,
    parameter_id: uuid.UUID,
) -> CpvValue | None:
    """获取特定批次和参数的值"""
    result = await db.execute(
        select(CpvValue).where(
            CpvValue.batch_id == batch_id,
            CpvValue.parameter_id == parameter_id,
            CpvValue.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def update_value(
    db: AsyncSession,
    batch_id: uuid.UUID,
    parameter_id: uuid.UUID,
    data: dict[str, Any],
) -> CpvValue | None:
    """更新参数值"""
    value = await get_value(db, batch_id, parameter_id)
    if not value:
        return None
    
    for key, val in data.items():
        setattr(value, key, val)
    
    await db.flush()
    return value


async def delete_values_by_batch_id(db: AsyncSession, batch_id: uuid.UUID) -> int:
    """删除批次的所有参数值（软删除）"""
    from sqlalchemy import update
    
    result = await db.execute(
        update(CpvValue)
        .where(
            CpvValue.batch_id == batch_id,
            CpvValue.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True)
    )
    return result.rowcount
