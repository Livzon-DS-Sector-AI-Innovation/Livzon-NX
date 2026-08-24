"""Validation service layer."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality.repository import validation as repository
from app.modules.quality.repository import validation_execution as execution_repository
from app.modules.quality.schemas.validation import (
    CreateValidationRequest,
    UpdateValidationExecutionRequest,
    UpdateValidationRequest,
    ValidationDetail,
    ValidationExecutionListItem,
    ValidationListItem,
)

logger = logging.getLogger(__name__)


def _build_validation_payload(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "validation_type": record.record_type,
        "record_code": record.record_code,
        "title": record.title,
        "status": record.status,
        "department": record.department,
        "equipment_code": record.equipment_code,
        "product_codes": record.product_codes,
        "planned_end_date": record.planned_end_date,
        "group_chat": record.group_chat,
        "participants": record.participants,
        "owner_name": record.owner_name,
        "plan_name": record.plan_name,
        "plan_code": record.plan_code,
        "drafted_at": record.drafted_at,
        "approved_at": record.approved_at,
        "report_no": record.report_no,
        "drafted_at_1": record.drafted_at_1,
        "approved_at_1": record.approved_at_1,
        "revalidation_cycle_years": record.revalidation_cycle_years,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "created_by": record.created_by,
        "updated_by": record.updated_by,
    }


def _build_validation_write_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.copy()
    validation_type = payload.pop("validation_type", None)
    if validation_type is not None:
        payload["record_type"] = validation_type
    return payload


async def get_validation_list(
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
) -> dict[str, Any]:
    items, total = await repository.get_validations(
        db,
        validation_type=validation_type,
        status=status,
        keyword=keyword,
        record_code=record_code,
        department=department,
        planned_end_date_from=planned_end_date_from,
        planned_end_date_to=planned_end_date_to,
        drafted_at_from=drafted_at_from,
        drafted_at_to=drafted_at_to,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            ValidationListItem(**_build_validation_payload(item)).model_dump()
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_validation_detail(
    db: AsyncSession,
    validation_id: uuid.UUID,
) -> ValidationDetail:
    record = await repository.get_validation_by_id(db, validation_id)
    if not record:
        raise ValueError(f"Validation {validation_id} not found")
    return ValidationDetail(**_build_validation_payload(record))


async def create_validation(
    db: AsyncSession,
    data: CreateValidationRequest,
    user_id: str,
) -> dict[str, Any]:
    if await repository.exists_by_record_code(db, data.record_code):
        raise ValueError(f"验证记录编号已存在: {data.record_code}")

    payload = _build_validation_write_payload(data.model_dump())
    if user_id != "system":
        payload["created_by"] = uuid.UUID(user_id)
        payload["updated_by"] = uuid.UUID(user_id)

    record = await repository.create_validation(db, payload)
    await execution_repository.upsert_execution_record_from_master(db, record)
    await db.commit()

    return ValidationDetail(**_build_validation_payload(record)).model_dump()


async def update_validation(
    db: AsyncSession,
    validation_id: uuid.UUID,
    data: UpdateValidationRequest,
    user_id: str,
) -> dict[str, Any]:
    record = await repository.get_validation_by_id(db, validation_id)
    if not record:
        raise ValueError(f"Validation {validation_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    if "record_code" in update_data and await repository.exists_by_record_code(
        db,
        update_data["record_code"],
        exclude_id=validation_id,
    ):
        raise ValueError(f"验证记录编号已存在: {update_data['record_code']}")

    payload = _build_validation_write_payload(update_data)
    if user_id != "system":
        payload["updated_by"] = uuid.UUID(user_id)

    updated = await repository.update_validation(db, record, payload)
    await execution_repository.upsert_execution_record_from_master(db, updated)
    await db.commit()

    return ValidationDetail(**_build_validation_payload(updated)).model_dump()


async def batch_delete_validations(
    db: AsyncSession,
    validation_ids: list[uuid.UUID],
) -> dict[str, int]:
    records = []
    for validation_id in validation_ids:
        record = await repository.get_validation_by_id(db, validation_id)
        if record:
            records.append(record)
    if not records:
        return {"deleted": 0}

    await repository.batch_delete_validation_records(db, records)
    for record in records:
        await execution_repository.delete_execution_records_for_master(db, record.id)
    await db.commit()

    return {"deleted": len(records)}


async def delete_validation(
    db: AsyncSession,
    validation_id: uuid.UUID,
) -> dict[str, bool]:
    record = await repository.get_validation_by_id(db, validation_id)
    if not record:
        raise ValueError(f"Validation {validation_id} not found")

    await repository.delete_validation(db, record)
    await execution_repository.delete_execution_records_for_master(db, validation_id)
    await db.commit()

    return {"success": True}


def _build_execution_payload(
    execution_record: Any,
    master_record: Any,
) -> dict[str, Any]:
    return {
        "id": execution_record.id,
        "master_validation_id": execution_record.master_validation_id,
        "title": execution_record.title,
        "status": master_record.status,
        "department": execution_record.department,
        "product_codes": execution_record.product_codes,
        "group_chat": execution_record.group_chat,
        "participants": execution_record.participants,
        "owner_name": execution_record.owner_name,
        "plan_name": execution_record.plan_name,
        "plan_code": execution_record.plan_code,
        "drafted_at": execution_record.drafted_at,
        "approved_at": execution_record.approved_at,
        "report_no": execution_record.report_no,
        "drafted_at_1": execution_record.drafted_at_1,
        "approved_at_1": execution_record.approved_at_1,
        "revalidation_cycle_years": execution_record.revalidation_cycle_years,
        "created_at": execution_record.created_at,
        "updated_at": execution_record.updated_at,
    }


async def get_validation_execution_list(
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
) -> dict[str, Any]:
    rows, total = await execution_repository.list_execution_records(
        db,
        validation_type=validation_type,
        status=status,
        keyword=keyword,
        department=department,
        drafted_at_from=drafted_at_from,
        drafted_at_to=drafted_at_to,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            ValidationExecutionListItem(
                **_build_execution_payload(execution_record, master_record)
            ).model_dump()
            for execution_record, master_record in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_validation_execution(
    db: AsyncSession,
    *,
    validation_type: str,
    record_id: uuid.UUID,
    data: UpdateValidationExecutionRequest,
    user_id: str,
) -> dict[str, Any]:
    record = await execution_repository.get_execution_record(
        db, validation_type, record_id
    )
    if not record:
        raise NotFoundException(resource="验证执行记录", resource_id=str(record_id))

    update_data = data.model_dump(exclude_unset=True)
    if user_id != "system":
        update_data["updated_by"] = uuid.UUID(user_id)

    updated = await execution_repository.update_execution_record(
        db,
        validation_type,
        record,
        update_data,
    )
    await db.commit()
    master_record = await repository.get_validation_by_id(
        db, updated.master_validation_id
    )
    if not master_record:
        raise NotFoundException(
            resource="验证记录", resource_id=str(updated.master_validation_id)
        )
    return ValidationExecutionListItem(
        **_build_execution_payload(updated, master_record)
    ).model_dump()


async def get_validation_statistics(
    db: AsyncSession,
) -> dict[str, Any]:
    """Return basic validation statistics from local database."""
    from sqlalchemy import func, select

    from app.modules.quality.models.validation_record import ValidationRecord

    base = select(ValidationRecord).where(ValidationRecord.is_deleted.is_(False))
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    by_type_rows = (
        await db.execute(
            select(ValidationRecord.record_type, func.count())
            .where(ValidationRecord.is_deleted.is_(False))
            .group_by(ValidationRecord.record_type)
        )
    ).all()
    by_status_rows = (
        await db.execute(
            select(ValidationRecord.status, func.count())
            .where(ValidationRecord.is_deleted.is_(False))
            .group_by(ValidationRecord.status)
        )
    ).all()

    return {
        "total": total,
        "by_type": {row[0]: row[1] for row in by_type_rows},
        "by_status": {row[0] or "未设置": row[1] for row in by_status_rows},
    }
