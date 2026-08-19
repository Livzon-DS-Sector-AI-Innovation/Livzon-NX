"""摇瓶种子制备记录 repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.seed_culture_models import SeedCulture


class SeedCultureRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        batch_no: str | None = None,
        product_name: str | None = None,
    ):
        query = select(SeedCulture).where(SeedCulture.is_deleted == False)

        if batch_no:
            query = query.where(SeedCulture.batch_no.ilike(f"%{batch_no}%"))
        if product_name:
            query = query.where(SeedCulture.product_name == product_name)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        query = query.order_by(SeedCulture.prepare_date.desc().nullslast(), SeedCulture.batch_no.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_id(self, record_id: UUID) -> SeedCulture | None:
        query = select(SeedCulture).where(SeedCulture.id == record_id, SeedCulture.is_deleted == False)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SeedCulture:
        record = SeedCulture(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def update(self, record_id: UUID, data: dict) -> SeedCulture | None:
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
