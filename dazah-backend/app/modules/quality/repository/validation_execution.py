"""Validation execution child repositories."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.quality.models.validation_execution_record import (
    CleaningValidationRecord,
    EquipmentQualificationRecord,
    OtherValidationRecord,
    ProcessValidationRecord,
    ValidationExecutionRecordBase,
)
from app.modules.quality.models.validation_record import ValidationRecord

ExecutionModel = type[ValidationExecutionRecordBase]

EXECUTION_MODEL_MAP: dict[str, ExecutionModel] = {
    "equipment_qualification": EquipmentQualificationRecord,
    "process_validation": ProcessValidationRecord,
    "cleaning_validation": CleaningValidationRecord,
    "other_validation": OtherValidationRecord,
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def get_execution_model(validation_type: str) -> ExecutionModel:
    model = EXECUTION_MODEL_MAP.get(validation_type)
    if model is None:
        raise ValueError(f"Unsupported validation type: {validation_type}")
    return model


def _build_execution_payload(master: ValidationRecord) -> dict:
    return {
        "id": master.id,
        "master_validation_id": master.id,
        "title": master.title,
        "product_codes": master.product_codes,
        "department": master.department,
        "group_chat": master.group_chat,
        "participants": master.participants,
        "owner_name": master.owner_name,
        "plan_name": master.plan_name,
        "plan_code": master.plan_code,
        "drafted_at": master.drafted_at,
        "approved_at": master.approved_at,
        "report_no": master.report_no,
        "drafted_at_1": master.drafted_at_1,
        "approved_at_1": master.approved_at_1,
        "revalidation_cycle_years": master.revalidation_cycle_years,
        "created_at": master.created_at,
        "updated_at": master.updated_at,
        "created_by": master.created_by,
        "updated_by": master.updated_by,
        "is_deleted": master.is_deleted,
    }


async def get_execution_record(
    db: AsyncSession,
    validation_type: str,
    record_id: uuid.UUID,
) -> ValidationExecutionRecordBase | None:
    model = get_execution_model(validation_type)
    result = await db.execute(
        select(model).where(
            model.id == record_id,
            model.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_execution_record_by_master_id(
    db: AsyncSession,
    validation_type: str,
    master_validation_id: uuid.UUID,
) -> ValidationExecutionRecordBase | None:
    model = get_execution_model(validation_type)
    result = await db.execute(
        select(model).where(
            model.master_validation_id == master_validation_id,
            model.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def upsert_execution_record_from_master(
    db: AsyncSession,
    master: ValidationRecord,
) -> ValidationExecutionRecordBase | None:
    validation_type = master.record_type
    if validation_type not in EXECUTION_MODEL_MAP:
        return None

    await delete_execution_records_except(db, master.id, keep_type=validation_type)
    model = get_execution_model(validation_type)
    payload = _build_execution_payload(master)
    record = await get_execution_record_by_master_id(db, validation_type, master.id)
    if record is None:
        record = model(**payload)
        db.add(record)
    else:
        for field, value in payload.items():
            setattr(record, field, value)
    await db.flush()
    await db.flush()
    return record


async def delete_execution_records_except(
    db: AsyncSession,
    master_validation_id: uuid.UUID,
    *,
    keep_type: str | None = None,
) -> None:
    for validation_type, model in EXECUTION_MODEL_MAP.items():
        if keep_type and validation_type == keep_type:
            continue
        result = await db.execute(
            select(model).where(
                model.master_validation_id == master_validation_id,
                model.is_deleted == False,
            )
        )
        record = result.scalar_one_or_none()
        if record is not None:
            record.is_deleted = True
    await db.flush()


async def delete_execution_records_for_master(
    db: AsyncSession,
    master_validation_id: uuid.UUID,
) -> None:
    await delete_execution_records_except(db, master_validation_id, keep_type=None)


async def update_execution_record(
    db: AsyncSession,
    validation_type: str,
    record: ValidationExecutionRecordBase,
    data: dict,
) -> ValidationExecutionRecordBase:
    get_execution_model(validation_type)
    for field, value in data.items():
        setattr(record, field, value)
    await db.flush()
    await db.flush()
    return record


async def list_execution_records(
    db: AsyncSession,
    *,
    validation_type: str,
    status: str | None = None,
    keyword: str | None = None,
    department: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[ValidationExecutionRecordBase, ValidationRecord]], int]:
    model = get_execution_model(validation_type)
    query = (
        select(model, ValidationRecord)
        .join(ValidationRecord, ValidationRecord.id == model.master_validation_id)
        .where(
            model.is_deleted == False,
            ValidationRecord.is_deleted == False,
        )
    )
    count_query = (
        select(func.count())
        .select_from(model)
        .join(ValidationRecord, ValidationRecord.id == model.master_validation_id)
        .where(
            model.is_deleted == False,
            ValidationRecord.is_deleted == False,
        )
    )

    filters = []
    if status:
        filters.append(ValidationRecord.status == status)
    if department:
        filters.append(model.department == department)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters.append(
            or_(
                model.title.ilike(pattern),
                model.department.ilike(pattern),
                model.plan_name.ilike(pattern),
                model.plan_code.ilike(pattern),
                model.report_no.ilike(pattern),
            )
        )
    drafted_from = _parse_date(drafted_at_from)
    if drafted_from:
        filters.append(model.drafted_at >= drafted_from)
    drafted_to = _parse_date(drafted_at_to)
    if drafted_to:
        filters.append(model.drafted_at <= drafted_to)

    for condition in filters:
        query = query.where(condition)
        count_query = count_query.where(condition)

    query = query.order_by(
        _coalesce_datetime(model.updated_at, ValidationRecord.updated_at).desc()
    ).offset((page - 1) * page_size).limit(page_size)

    total = (await db.execute(count_query)).scalar_one()
    rows = (await db.execute(query)).all()
    return rows, total


def _coalesce_datetime(
    primary: InstrumentedAttribute,
    fallback: InstrumentedAttribute,
):
    return func.coalesce(primary, fallback)
