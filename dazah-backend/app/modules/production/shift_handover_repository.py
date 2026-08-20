"""班组交接确认 repository."""

import builtins
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.shift_handover_models import ShiftHandover


class ShiftHandoverRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        position: str | None = None,
        workshop: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        query = select(ShiftHandover).where(not ShiftHandover.is_deleted)

        if position:
            query = query.where(ShiftHandover.position == position)
        if workshop:
            query = query.where(ShiftHandover.workshop == workshop)
        if date_from:
            query = query.where(ShiftHandover.handover_time >= date_from)
        if date_to:
            query = query.where(ShiftHandover.handover_time <= date_to)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        query = query.order_by(ShiftHandover.handover_time.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_id(self, record_id: UUID) -> ShiftHandover | None:
        query = select(ShiftHandover).where(
            ShiftHandover.id == record_id,
            not ShiftHandover.is_deleted,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> ShiftHandover:
        record = ShiftHandover(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def update(self, record_id: UUID, data: dict) -> ShiftHandover | None:
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

    async def confirm(self, record_id: UUID) -> ShiftHandover | None:
        record = await self.get_by_id(record_id)
        if not record:
            return None
        record.status = "confirmed"
        record.confirmed_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_distinct_positions(self) -> builtins.list[str]:
        query = (
            select(ShiftHandover.position)
            .where(not ShiftHandover.is_deleted)
            .distinct()
            .order_by(ShiftHandover.position)
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]
