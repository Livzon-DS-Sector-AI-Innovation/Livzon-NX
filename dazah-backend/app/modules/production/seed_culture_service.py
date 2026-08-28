"""摇瓶种子制备记录 service."""
from datetime import date as date_type
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.seed_culture_repository import SeedCultureRepository


class SeedCultureService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = SeedCultureRepository(session)

    @staticmethod
    def _prepare_data(data: dict[str, Any]) -> dict[str, Any]:
        for field in ("prepare_date", "shaker_start_date"):
            if (
                field in data
                and data[field] is not None
                and isinstance(data[field], str)
            ):
                data[field] = date_type.fromisoformat(data[field])
        return data

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        batch_no: str | None = None,
        product_name: str | None = None,
    ) -> Any:
        return await self.repo.list(
            page=page, page_size=page_size, batch_no=batch_no, product_name=product_name
        )

    async def get_record(self, record_id: UUID) -> Any:
        return await self.repo.get_by_id(record_id)

    async def create_record(self, data: dict[str, Any]) -> Any:
        return await self.repo.create(self._prepare_data(data))

    async def update_record(self, record_id: UUID, data: dict[str, Any]) -> Any:
        record = await self.repo.update(record_id, self._prepare_data(data))
        if not record:
            raise ValueError(f"Seed culture {record_id} not found")
        return record

    async def delete_record(self, record_id: UUID) -> Any:
        if not await self.repo.delete(record_id):
            raise ValueError(f"Seed culture {record_id} not found")
