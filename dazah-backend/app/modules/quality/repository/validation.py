"""Validation repository."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


async def exists_by_record_code(
    db: AsyncSession,
    record_code: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    query = select(ValidationRecord.id).where(
        ValidationRecord.record_code == record_code,
        ValidationRecord.is_deleted == False,
    )
    if exclude_id is not None:
        query = query.where(ValidationRecord.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


async def create_validation(
    db: AsyncSession,
    data: dict,
) -> ValidationRecord:
    record = ValidationRecord(**data)
    db.add(record)
    await db.flush()
    await db.flush()
    return record


async def get_validation_by_id(
    db: AsyncSession,
    validation_id: uuid.UUID,
) -> ValidationRecord | None:
    result = await db.execute(
        select(ValidationRecord).where(
            ValidationRecord.id == validation_id,
            ValidationRecord.is_deleted == False,
        ).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def update_validation(
    db: AsyncSession,
    record: ValidationRecord,
    data: dict,
) -> ValidationRecord:
    for field, value in data.items():
        setattr(record, field, value)
    await db.flush()
    await db.flush()
    return record


async def delete_validation(
    db: AsyncSession,
    record: ValidationRecord,
) -> None:
    record.is_deleted = True
    await db.flush()


async def batch_delete_validation_records(
    db: AsyncSession,
    records: list[ValidationRecord],
) -> int:
    for record in records:
        record.is_deleted = True
    await db.flush()
    return len(records)


async def batch_delete_validations(
    db: AsyncSession,
    ids: list[uuid.UUID],
) -> int:
    """批量软删除验证记录"""
    result = await db.execute(
        select(ValidationRecord).where(
            ValidationRecord.id.in_(ids),
            ValidationRecord.is_deleted == False,
        )
    )
    records = result.scalars().all()
    for record in records:
        record.is_deleted = True
    await db.flush()
    return len(records)


async def get_validations(
    db: AsyncSession,
    *,
    validation_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    record_code: str | None = None,
    department: str | None = None,
    planned_end_date_from: str | None = None,
    planned_end_date_to: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ValidationRecord], int]:
    query = select(ValidationRecord).where(ValidationRecord.is_deleted == False)
    count_query = select(func.count()).select_from(ValidationRecord).where(
        ValidationRecord.is_deleted == False
    )

    filters = []
    if validation_type:
        filters.append(ValidationRecord.record_type == validation_type)
    if status:
        filters.append(ValidationRecord.status == status)
    if department:
        filters.append(ValidationRecord.department == department)
    if record_code:
        filters.append(
            ValidationRecord.record_code.ilike(f"%{_escape_like(record_code)}%")
        )
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters.append(
            or_(
                ValidationRecord.record_code.ilike(pattern),
                ValidationRecord.title.ilike(pattern),
                ValidationRecord.department.ilike(pattern),
                ValidationRecord.equipment_code.ilike(pattern),
                ValidationRecord.plan_code.ilike(pattern),
            )
        )

    # 日期范围筛选
    planned_end_date_from_date = _parse_date(planned_end_date_from)
    planned_end_date_to_date = _parse_date(planned_end_date_to)
    if planned_end_date_from_date:
        filters.append(ValidationRecord.planned_end_date >= planned_end_date_from_date)
    if planned_end_date_to_date:
        filters.append(ValidationRecord.planned_end_date <= planned_end_date_to_date)

    drafted_at_from_date = _parse_date(drafted_at_from)
    drafted_at_to_date = _parse_date(drafted_at_to)
    if drafted_at_from_date:
        filters.append(ValidationRecord.drafted_at >= drafted_at_from_date)
    if drafted_at_to_date:
        filters.append(ValidationRecord.drafted_at <= drafted_at_to_date)

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(ValidationRecord.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all(), total
