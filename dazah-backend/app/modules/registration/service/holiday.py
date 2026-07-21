"""Holiday service: business logic."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.registration import repository as repo
from app.modules.registration.models.drug import Holiday
from app.modules.registration.schemas.holiday import HolidayCreate


async def create_holiday(db: AsyncSession, data: HolidayCreate) -> Holiday:
    """创建节假日"""
    return await repo.create_holiday(db, data.model_dump())


async def get_holidays(db: AsyncSession, year: int | None = None) -> list[Holiday]:
    """获取节假日列表"""
    return await repo.get_holidays(db, year)


async def update_holiday(
    db: AsyncSession,
    holiday_id: uuid.UUID,
    data: HolidayCreate,
) -> Holiday:
    """更新节假日"""
    holiday = await repo.get_holiday_by_id(db, holiday_id)
    if not holiday:
        raise NotFoundException("节假日", str(holiday_id))
    updated = await repo.update_holiday(db, holiday_id, data.model_dump())
    if not updated:
        raise NotFoundException("节假日", str(holiday_id))
    return updated


async def delete_holiday(db: AsyncSession, holiday_id: uuid.UUID) -> None:
    """删除节假日"""
    holiday = await repo.get_holiday_by_id(db, holiday_id)
    if not holiday:
        raise NotFoundException("节假日", str(holiday_id))
    await repo.delete_holiday(db, holiday_id)
