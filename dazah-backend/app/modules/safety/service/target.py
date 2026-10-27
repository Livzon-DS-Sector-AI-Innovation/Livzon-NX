"""目标责任与绩效：年度安全目标与进度记录的查询与维护。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import SafetyTarget, SafetyTargetRecord
from app.modules.safety.schemas.targets import (
    SafetyTargetCreate,
    SafetyTargetDepartmentStat,
    SafetyTargetRecordCreate,
    SafetyTargetRecordUpdate,
    SafetyTargetStatsResponse,
    SafetyTargetUpdate,
)


def build_search_text(
    title: str, category: str, owner_department: str, owner_name: str, metric: str
) -> str:
    return " ".join(
        part for part in (title, category, owner_department, owner_name, metric) if part
    )


class SafetyTargetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_targets(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        year: int | None = None,
        category: str | None = None,
        department: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[SafetyTarget], int]:
        conditions: list[ColumnElement[bool]] = [SafetyTarget.is_deleted.is_(False)]
        if year is not None:
            conditions.append(SafetyTarget.year == year)
        if category:
            conditions.append(SafetyTarget.category == category)
        if department:
            conditions.append(SafetyTarget.owner_department == department)
        if status:
            conditions.append(SafetyTarget.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    SafetyTarget.title.ilike(pattern),
                    SafetyTarget.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count()).select_from(SafetyTarget).where(*conditions)
            )
        ).scalar() or 0

        result = await self.db.execute(
            select(SafetyTarget)
            .options(selectinload(SafetyTarget.records))
            .where(*conditions)
            .order_by(
                SafetyTarget.year.desc(),
                SafetyTarget.category.asc(),
                SafetyTarget.created_at.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().unique().all()), total

    async def get_target(self, target_id: UUID) -> SafetyTarget | None:
        result = await self.db.execute(
            select(SafetyTarget)
            .options(selectinload(SafetyTarget.records))
            .where(
                SafetyTarget.id == target_id,
                SafetyTarget.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, year: int, title: str, owner_department: str
    ) -> SafetyTarget | None:
        result = await self.db.execute(
            select(SafetyTarget).where(
                SafetyTarget.year == year,
                SafetyTarget.title == title,
                SafetyTarget.owner_department == owner_department,
                SafetyTarget.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_target(
        self, data: SafetyTargetCreate, user_id: UUID | None = None
    ) -> SafetyTarget:
        if await self.get_by_key(data.year, data.title, data.owner_department):
            raise AppException(
                status_code=409, message="同年度/部门下已存在同名安全目标"
            )
        target = SafetyTarget(
            year=data.year,
            title=data.title,
            category=data.category,
            metric=data.metric,
            target_value=data.target_value,
            unit=data.unit,
            owner_department=data.owner_department,
            owner_name=data.owner_name,
            deadline=data.deadline,
            status=data.status,
            remark=data.remark,
            search_text=build_search_text(
                data.title,
                data.category,
                data.owner_department,
                data.owner_name,
                data.metric,
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(target)
        await self.db.flush()
        return target

    async def update_target(
        self, target_id: UUID, data: SafetyTargetUpdate, user_id: UUID | None = None
    ) -> SafetyTarget:
        target = await self.get_target(target_id)
        if target is None:
            raise NotFoundException("安全目标不存在")

        changes = data.model_dump(exclude_unset=True)
        new_year = changes.get("year", target.year)
        new_title = changes.get("title", target.title)
        new_department = changes.get("owner_department", target.owner_department)
        if (new_year, new_title, new_department) != (
            target.year,
            target.title,
            target.owner_department,
        ):
            existing = await self.get_by_key(new_year, new_title, new_department)
            if existing is not None and existing.id != target.id:
                raise AppException(
                    status_code=409, message="同年度/部门下已存在同名安全目标"
                )
        for field, value in changes.items():
            setattr(target, field, value)
        target.search_text = build_search_text(
            target.title,
            target.category,
            target.owner_department,
            target.owner_name,
            target.metric,
        )
        target.updated_by = user_id
        await self.db.flush()
        return target

    async def delete_target(self, target_id: UUID) -> bool:
        target = await self.get_target(target_id)
        if target is None:
            return False
        target.is_deleted = True
        await self.db.flush()
        return True

    async def create_record(
        self,
        target_id: UUID,
        data: SafetyTargetRecordCreate,
        user_id: UUID | None = None,
    ) -> SafetyTargetRecord:
        target = await self.get_target(target_id)
        if target is None:
            raise NotFoundException("安全目标不存在")
        existing = await self.get_record(target_id, data.period)
        if existing is not None:
            raise AppException(
                status_code=409, message="该考核期已有进度记录，请直接编辑"
            )
        record = SafetyTargetRecord(
            target_id=target_id,
            period=data.period,
            actual_value=data.actual_value,
            completion_pct=data.completion_pct,
            note=data.note,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_record(
        self, target_id: UUID, period: str
    ) -> SafetyTargetRecord | None:
        result = await self.db.execute(
            select(SafetyTargetRecord).where(
                SafetyTargetRecord.target_id == target_id,
                SafetyTargetRecord.period == period,
                SafetyTargetRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update_record(
        self,
        target_id: UUID,
        period: str,
        data: SafetyTargetRecordUpdate,
        user_id: UUID | None = None,
    ) -> SafetyTargetRecord:
        record = await self.get_record(target_id, period)
        if record is None:
            raise NotFoundException("进度记录不存在")
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(record, field, value)
        record.updated_by = user_id
        await self.db.flush()
        return record

    async def delete_record(self, target_id: UUID, period: str) -> bool:
        record = await self.get_record(target_id, period)
        if record is None:
            return False
        record.is_deleted = True
        await self.db.flush()
        return True

    async def get_stats(self, *, year: int | None = None) -> SafetyTargetStatsResponse:
        conditions: list[ColumnElement[bool]] = [SafetyTarget.is_deleted.is_(False)]
        if year is not None:
            conditions.append(SafetyTarget.year == year)
        result = await self.db.execute(
            select(
                SafetyTarget.category,
                SafetyTarget.owner_department,
                SafetyTarget.status,
            ).where(*conditions)
        )
        rows = result.all()

        category_order: list[str] = []
        department_rows: dict[str, list[str]] = {}
        for category, department, status in rows:
            if category not in category_order:
                category_order.append(category)
            if department:
                department_rows.setdefault(department, []).append(status)

        departments = [
            SafetyTargetDepartmentStat(
                department=department,
                total=len(statuses),
                achieved=sum(1 for s in statuses if s == "achieved"),
                not_achieved=sum(1 for s in statuses if s == "not_achieved"),
                in_progress=sum(1 for s in statuses if s == "in_progress"),
            )
            for department, statuses in department_rows.items()
        ]
        return SafetyTargetStatsResponse(
            total=len(rows),
            achieved=sum(1 for _, _, s in rows if s == "achieved"),
            in_progress=sum(1 for _, _, s in rows if s == "in_progress"),
            not_achieved=sum(1 for _, _, s in rows if s == "not_achieved"),
            categories=category_order,
            departments=departments,
        )
