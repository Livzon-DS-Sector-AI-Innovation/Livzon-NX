"""培训计划跟踪 Repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import PlanTrackingRecord


class PlanTrackingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        plan_id: UUID | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[PlanTrackingRecord], int]:
        query = select(PlanTrackingRecord).where(
            PlanTrackingRecord.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(PlanTrackingRecord)
            .where(PlanTrackingRecord.is_deleted.is_(False))
        )

        if dept_alias_set is not None:
            # 部门级数据隔离：公司级（department
            # 为空）记录保留可见，部门级按可见范围过滤
            scope = or_(
                PlanTrackingRecord.department.is_(None),
                PlanTrackingRecord.department == "",
                PlanTrackingRecord.department.in_(dept_alias_set),
            )
            query = query.where(scope)
            count_query = count_query.where(scope)

        if plan_id:
            query = query.where(PlanTrackingRecord.plan_id == plan_id)
            count_query = count_query.where(PlanTrackingRecord.plan_id == plan_id)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(
            PlanTrackingRecord.sort_order.asc(), PlanTrackingRecord.created_at.desc()
        )
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        records = list(result.scalars().all())
        return records, total

    async def get_by_id(self, record_id: UUID) -> PlanTrackingRecord | None:
        query = select(PlanTrackingRecord).where(
            PlanTrackingRecord.id == record_id,
            PlanTrackingRecord.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_period(
        self,
        year: int,
        month: int,
        plan_level: str,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> list[PlanTrackingRecord]:
        """按 年+月+级别(+部门) 查询跟踪记录，不分页."""
        query = select(PlanTrackingRecord).where(
            PlanTrackingRecord.is_deleted.is_(False),
            PlanTrackingRecord.year == year,
            PlanTrackingRecord.month == str(month),
            PlanTrackingRecord.plan_level == plan_level,
        )
        # 部门级且指定了部门时按部门过滤；未指定时跨部门汇总
        if plan_level == "部门级" and department:
            query = query.where(PlanTrackingRecord.department == department)
        elif plan_level == "部门级" and dept_alias_set is not None:
            # 部门级数据隔离：部门级汇总仅包含可见部门
            query = query.where(PlanTrackingRecord.department.in_(dept_alias_set))
        query = query.order_by(
            PlanTrackingRecord.sort_order.asc(), PlanTrackingRecord.created_at.asc()
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_plan_item(self, plan_item_id: UUID) -> PlanTrackingRecord | None:
        """按来源计划明细ID查询（自动录入去重）."""
        query = select(PlanTrackingRecord).where(
            PlanTrackingRecord.plan_item_id == plan_item_id,
            PlanTrackingRecord.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, record: PlanTrackingRecord) -> PlanTrackingRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(
        self, record: PlanTrackingRecord, data: dict[str, Any]
    ) -> PlanTrackingRecord:
        for key, value in data.items():
            if value is not None:
                setattr(record, key, value)
        await self.session.flush()
        return record

    async def delete(self, record: PlanTrackingRecord) -> None:
        record.is_deleted = True
        await self.session.flush()
