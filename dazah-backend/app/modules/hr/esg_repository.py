"""ESG 培训报表 Repository."""

from datetime import date
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import EsgTrainingRecord


class EsgTrainingRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> EsgTrainingRecord | None:
        result = await self.session.execute(
            select(EsgTrainingRecord).where(
                EsgTrainingRecord.id == record_id,
                EsgTrainingRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_department(
        self,
        department: str,
        page: int = 1,
        page_size: int = 200,
        sort_by: str = "training_date",
        sort_order: str = "desc",
    ) -> tuple[list[EsgTrainingRecord], int]:
        stmt = select(EsgTrainingRecord).where(
            EsgTrainingRecord.department == department,
            EsgTrainingRecord.is_deleted.is_(False),
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        sort_column = getattr(
            EsgTrainingRecord, sort_by, EsgTrainingRecord.training_date
        )
        order_func = desc if sort_order == "desc" else asc
        data_stmt = (
            stmt.order_by(order_func(sort_column))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        data_result = await self.session.execute(data_stmt)
        return list(data_result.scalars().all()), total

    async def create(self, record: EsgTrainingRecord) -> EsgTrainingRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, record: EsgTrainingRecord) -> EsgTrainingRecord:
        await self.session.flush()
        result = await self.session.execute(
            select(EsgTrainingRecord).where(
                EsgTrainingRecord.id == record.id,
                EsgTrainingRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one()

    async def soft_delete(self, record: EsgTrainingRecord) -> None:
        record.is_deleted = True
        await self.session.flush()

    async def exists_by_key(
        self, training_date: date, training_name: str, employee_name: str
    ) -> bool:
        """按 (培训日期, 培训名称, 姓名) 三元组检查是否已存在 ESG 记录."""
        return (
            await self.get_by_key(training_date, training_name, employee_name)
            is not None
        )

    async def get_by_key(
        self, training_date: date, training_name: str, employee_name: str
    ) -> EsgTrainingRecord | None:
        """按 (培训日期, 培训名称, 姓名) 三元组查找已存在的 ESG 记录."""
        result = await self.session.execute(
            select(EsgTrainingRecord).where(
                EsgTrainingRecord.training_date == training_date,
                EsgTrainingRecord.training_name == training_name,
                EsgTrainingRecord.employee_name == employee_name,
                EsgTrainingRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()
