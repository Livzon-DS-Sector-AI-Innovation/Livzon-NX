"""班组交接确认 service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.shift_handover_repository import ShiftHandoverRepository


class ShiftHandoverService:
    def __init__(self, session: AsyncSession):
        self.repo = ShiftHandoverRepository(session)

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        position: str | None = None,
        workshop: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        return await self.repo.list(
            page=page,
            page_size=page_size,
            position=position,
            workshop=workshop,
            date_from=date_from,
            date_to=date_to,
        )

    async def get_record(self, record_id: UUID):
        return await self.repo.get_by_id(record_id)

    async def create_record(self, data: dict):
        return await self.repo.create(data)

    async def update_record(self, record_id: UUID, data: dict):
        record = await self.repo.update(record_id, data)
        if not record:
            raise ValueError(f"Shift handover {record_id} not found")
        return record

    async def delete_record(self, record_id: UUID):
        if not await self.repo.delete(record_id):
            raise ValueError(f"Shift handover {record_id} not found")

    async def confirm_record(self, record_id: UUID):
        record = await self.repo.confirm(record_id)
        if not record:
            raise ValueError(f"Shift handover {record_id} not found")
        return record

    async def get_distinct_positions(self):
        return await self.repo.get_distinct_positions()
