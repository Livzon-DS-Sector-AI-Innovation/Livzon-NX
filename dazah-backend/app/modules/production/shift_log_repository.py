"""生产日志与交接班 repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.shift_log_models import ShiftLog


class ShiftLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        workshop: str | None = None,
        shift: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        query = select(ShiftLog).where(ShiftLog.is_deleted.is_(False))

        if workshop:
            query = query.where(ShiftLog.workshop == workshop)
        if shift:
            query = query.where(ShiftLog.shift == shift)
        if date_from:
            query = query.where(ShiftLog.log_date >= date_from)
        if date_to:
            query = query.where(ShiftLog.log_date <= date_to)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        # Paginate
        query = query.order_by(ShiftLog.log_date.desc(), ShiftLog.shift.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_id(self, record_id: UUID) -> ShiftLog | None:
        query = select(ShiftLog).where(
            ShiftLog.id == record_id,
            ShiftLog.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> ShiftLog:
        record = ShiftLog(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def update(self, record_id: UUID, data: dict) -> ShiftLog | None:
        record = await self.get_by_id(record_id)
        if not record:
            return None
        for key, value in data.items():
            setattr(record, key, value)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def delete(self, record_id: UUID) -> bool:
        record = await self.get_by_id(record_id)
        if not record:
            return False
        record.is_deleted = True
        await self.session.flush()
        return True
