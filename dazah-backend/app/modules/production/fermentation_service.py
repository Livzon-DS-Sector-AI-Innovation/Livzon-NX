"""Fermentation record service."""

from datetime import date as date_type
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.fermentation_repository import FermentationRepository


class FermentationService:
    def __init__(self, session: AsyncSession):
        self.repo = FermentationRepository(session)

    @staticmethod
    def _prepare_data(data: dict) -> dict:
        """Convert string dates to date objects."""
        for field in ("entry_date", "discharge_date"):
            if field in data and data[field] is not None:
                if isinstance(data[field], str):
                    data[field] = date_type.fromisoformat(data[field])
        return data

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        product_name: str | None = None,
        batch_no: str | None = None,
        status: str | None = None,
        fermenter: str | None = None,
    ):
        return await self.repo.list(
            page=page,
            page_size=page_size,
            product_name=product_name,
            batch_no=batch_no,
            status=status,
            fermenter=fermenter,
        )

    async def get_record(self, record_id: UUID):
        return await self.repo.get_by_id(record_id)

    async def create_record(self, data: dict):
        return await self.repo.create(self._prepare_data(data))

    async def update_record(self, record_id: UUID, data: dict):
        record = await self.repo.update(record_id, self._prepare_data(data))
        if not record:
            raise ValueError(f"Fermentation record {record_id} not found")
        return record

    async def delete_record(self, record_id: UUID):
        if not await self.repo.delete(record_id):
            raise ValueError(f"Fermentation record {record_id} not found")

    async def update_status(self, record_id: UUID, status: str):
        record = await self.repo.update(record_id, {"status": status})
        if not record:
            raise ValueError(f"Fermentation record {record_id} not found")
        return record
