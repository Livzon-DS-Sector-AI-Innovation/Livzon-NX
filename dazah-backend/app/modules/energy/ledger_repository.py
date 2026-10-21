"""Native ledger persistence and transaction-scoped serialization."""

from datetime import date
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import (
    EnergyEntryTask,
    EnergyPeriodLock,
    EnergyReading,
    LedgerBase,
)

Record = TypeVar("Record", bound=LedgerBase)


class EnergyLedgerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def serialize_write(self) -> None:
        # Also serializes sealing against adjacent-month counter corrections.
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

    async def month_lock(self, month: str) -> EnergyPeriodLock:
        item = await self.db.scalar(
            select(EnergyPeriodLock).where(EnergyPeriodLock.month == month)
        )
        if item is None:
            item = EnergyPeriodLock(month=month, locked=False, version=0, snapshot=[])
            self.db.add(item)
            await self.db.flush()
        return item

    async def assert_unlocked(self, days: set[date]) -> None:
        months = {day.strftime("%Y-%m") for day in days}
        locked = await self.db.scalar(
            select(EnergyPeriodLock.month).where(
                EnergyPeriodLock.month.in_(months), EnergyPeriodLock.locked.is_(True)
            )
        )
        if locked:
            raise AppException(409, f"{locked} 已封账，须由能源管理员解锁后更正")

    async def task_readings(self, task_id: UUID) -> list[EnergyReading]:
        return list(
            (
                await self.db.scalars(
                    select(EnergyReading)
                    .where(EnergyReading.task_id == task_id)
                    .order_by(EnergyReading.reading_date, EnergyReading.point_id)
                )
            ).all()
        )

    async def task_for(self, plan_id: UUID, day: date) -> EnergyEntryTask | None:
        result = await self.db.scalars(
            select(EnergyEntryTask).where(
                EnergyEntryTask.plan_id == plan_id, EnergyEntryTask.task_date == day
            )
        )
        return result.one_or_none()
