"""非密事件与运行偏差 repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.nce_models import NonConformingEvent


class NCERepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, page=1, page_size=20, workshop=None, event_type=None, date_from=None, date_to=None):
        query = select(NonConformingEvent).where(NonConformingEvent.is_deleted == False)
        if workshop:
            query = query.where(NonConformingEvent.workshop == workshop)
        if event_type:
            query = query.where(NonConformingEvent.event_type == event_type)
        if date_from:
            query = query.where(NonConformingEvent.event_time >= date_from)
        if date_to:
            query = query.where(NonConformingEvent.event_time <= date_to)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        query = query.order_by(NonConformingEvent.event_time.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, record_id: UUID) -> NonConformingEvent | None:
        query = select(NonConformingEvent).where(NonConformingEvent.id == record_id, NonConformingEvent.is_deleted == False)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> NonConformingEvent:
        record = NonConformingEvent(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def update(self, record_id: UUID, data: dict) -> NonConformingEvent | None:
        record = await self.get_by_id(record_id)
        if not record:
            return None
        for k, v in data.items():
            setattr(record, k, v)
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
