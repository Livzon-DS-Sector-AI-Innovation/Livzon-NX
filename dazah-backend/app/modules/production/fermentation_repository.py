"""Fermentation record repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.fermentation_models import FermentationRecord


class FermentationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        product_name: str | None = None,
        batch_no: str | None = None,
        status: str | None = None,
        fermenter: str | None = None,
    ):
        query = select(FermentationRecord).where(FermentationRecord.is_deleted.is_(False))  # noqa: E501

        if product_name:
            query = query.where(FermentationRecord.product_name == product_name)
        if batch_no:
            query = query.where(FermentationRecord.batch_no.ilike(f"%{batch_no}%"))
        if status:
            query = query.where(FermentationRecord.status == status)
        if fermenter:
            query = query.where(FermentationRecord.fermenter.ilike(f"%{fermenter}%"))

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        # Paginate
        query = query.order_by(FermentationRecord.entry_date.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_id(self, record_id: UUID) -> FermentationRecord | None:
        query = select(FermentationRecord).where(
            FermentationRecord.id == record_id,
            FermentationRecord.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> FermentationRecord:
        record = FermentationRecord(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.commit()
        # refresh after commit to ensure DB-generated defaults are loaded
        await self.session.refresh(record)
        return record

    async def update(self, record_id: UUID, data: dict) -> FermentationRecord | None:
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
