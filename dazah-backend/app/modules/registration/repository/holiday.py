"""Holiday database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models.drug import Holiday


async def create_holiday(db: AsyncSession, data: dict[str, Any]) -> Holiday:
    """创建节假日"""
    holiday = Holiday(**data)
    db.add(holiday)
    await db.flush()
    return holiday


async def get_holidays(db: AsyncSession, year: int | None = None) -> list[Holiday]:
    """获取节假日列表"""
    query = select(Holiday).where(Holiday.is_deleted == False)  # noqa: E712
    if year:
        query = query.where(Holiday.year == year)
    query = query.order_by(Holiday.date)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_holiday_by_id(db: AsyncSession, holiday_id: uuid.UUID) -> Holiday | None:
    """根据ID获取节假日"""
    query = select(Holiday).where(
        Holiday.id == holiday_id,
        Holiday.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_holiday(
    db: AsyncSession,
    holiday_id: uuid.UUID,
    data: dict[str, Any],
) -> Holiday | None:
    """更新节假日"""
    holiday = await get_holiday_by_id(db, holiday_id)
    if not holiday:
        return None
    for key, value in data.items():
        if hasattr(holiday, key):
            setattr(holiday, key, value)
    await db.flush()
    return holiday


async def delete_holiday(db: AsyncSession, holiday_id: uuid.UUID) -> bool:
    """删除节假日"""
    holiday = await get_holiday_by_id(db, holiday_id)
    if not holiday:
        return False
    holiday.is_deleted = True
    await db.flush()
    return True
