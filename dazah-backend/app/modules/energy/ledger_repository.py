"""Native ledger persistence and transaction-scoped serialization."""

from typing import TypeVar
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import (
    LedgerBase,
)

Record = TypeVar("Record", bound=LedgerBase)


class EnergyLedgerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def serialize_write(self) -> None:
        # Serializes configuration, import and reading writes across workers.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('energy.native-ledger'))")
        )

    async def all(self, model: type[Record]) -> list[Record]:
        result = await self.db.scalars(
            select(model)
            .where(model.is_deleted.is_(False))
            .order_by(model.created_at, model.id)
            .limit(2001)
        )
        items = list(result.all())
        if len(items) > 2000:
            raise AppException(409, "配置或任务超过单次处理上限，请缩小范围")
        return items

    async def get(self, model: type[Record], record_id: UUID) -> Record:
        item = await self.db.get(model, record_id)
        if item is None or item.is_deleted:
            raise AppException(404, "能源记录不存在")
        return item
