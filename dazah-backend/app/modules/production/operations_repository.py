"""发酵与生产日志的通用软删除仓储。"""

import uuid
from typing import Any, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.base_model import BaseModel

T = TypeVar("T", bound=BaseModel)


class OperationsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_records(
        self,
        model: type[T],
        *,
        skip: int,
        limit: int,
        filters: dict[str, Any] | None = None,
        searches: dict[str, str] | None = None,
        order_by: str = "created_at",
    ) -> tuple[list[T], int]:
        clauses = [model.is_deleted.is_(False)]
        for field, value in (filters or {}).items():
            if value is not None:
                clauses.append(getattr(model, field) == value)
        for field, value in (searches or {}).items():
            if value:
                clauses.append(getattr(model, field).ilike(f"%{value}%"))
        total = await self.session.scalar(select(func.count(model.id)).where(*clauses))
        result = await self.session.execute(
            select(model)
            .where(*clauses)
            .order_by(getattr(model, order_by).desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total or 0

    async def get(self, model: type[T], record_id: uuid.UUID) -> T | None:
        result = await self.session.execute(
            select(model).where(model.id == record_id, model.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_by_source(
        self, model: type[T], source: str, source_record_id: str
    ) -> T | None:
        result = await self.session.execute(
            select(model).where(
                model.source == source,
                model.source_record_id == source_record_id,
                model.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, model: type[T], data: dict[str, Any]) -> T:
        record = model(**data)
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(
        self, model: type[T], record_id: uuid.UUID, data: dict[str, Any]
    ) -> T | None:
        result = await self.session.execute(
            update(model)
            .where(model.id == record_id, model.is_deleted.is_(False))
            .values(**data)
            .returning(model.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get(model, record_id)

    async def soft_delete(self, model: type[T], record_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(model)
            .where(model.id == record_id, model.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        return (result.rowcount or 0) > 0
