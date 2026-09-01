"""ESG 培训报表 Repository."""

from datetime import date
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import EsgTrainingRecord
from app.modules.hr.schemas import EsgListFilters

# 文本列 → 模糊匹配（ilike 包含）；其余筛选列为精确匹配
_FUZZY_COLUMNS = (
    "training_name",
    "employee_name",
    "employee_account",
    "apply_company",
    "apply_company_no",
    "remarks",
)


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
        date_from: date | None = None,
        date_to: date | None = None,
        filters: EsgListFilters | None = None,
    ) -> tuple[list[EsgTrainingRecord], int]:
        stmt = select(EsgTrainingRecord).where(
            EsgTrainingRecord.department == department,
            EsgTrainingRecord.is_deleted.is_(False),
        )
        if date_from:
            stmt = stmt.where(EsgTrainingRecord.training_date >= date_from)
        if date_to:
            stmt = stmt.where(EsgTrainingRecord.training_date <= date_to)

        if filters is not None and filters.has_any():
            values = filters.model_dump()
            for column in _FUZZY_COLUMNS:
                text_value = values.get(column)
                if text_value:
                    stmt = stmt.where(
                        getattr(EsgTrainingRecord, column).ilike(f"%{text_value}%")
                    )
            for column in (
                "training_method",
                "caliber",
                "training_type",
                "location_address",
                "employee_level",
                "gender",
            ):
                text_value = values.get(column)
                if text_value:
                    stmt = stmt.where(getattr(EsgTrainingRecord, column) == text_value)
            if values.get("age_min") is not None:
                stmt = stmt.where(EsgTrainingRecord.age >= values["age_min"])
            if values.get("age_max") is not None:
                stmt = stmt.where(EsgTrainingRecord.age <= values["age_max"])
            if values.get("duration_min") is not None:
                stmt = stmt.where(
                    EsgTrainingRecord.duration >= values["duration_min"]
                )
            if values.get("duration_max") is not None:
                stmt = stmt.where(
                    EsgTrainingRecord.duration <= values["duration_max"]
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

    async def filter_options(
        self,
        department: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, list[str]]:
        """部门+日期范围内各枚举列的去重选项（供前端筛选下拉）."""
        columns = (
            "training_method",
            "caliber",
            "training_type",
            "location_address",
            "employee_level",
            "gender",
            "apply_company",
        )
        base = select(EsgTrainingRecord).where(
            EsgTrainingRecord.department == department,
            EsgTrainingRecord.is_deleted.is_(False),
        )
        if date_from:
            base = base.where(EsgTrainingRecord.training_date >= date_from)
        if date_to:
            base = base.where(EsgTrainingRecord.training_date <= date_to)

        options: dict[str, list[str]] = {}
        for column in columns:
            stmt = (
                base.with_only_columns(getattr(EsgTrainingRecord, column))
                .distinct()
                .order_by(getattr(EsgTrainingRecord, column))
            )
            result = await self.session.execute(stmt)
            options[column] = [row[0] for row in result.all() if row[0] is not None]
        return options

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
