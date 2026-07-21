from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord
from app.modules.quality.schemas.validation import (
    CreateValidationRequest,
    UpdateValidationRequest,
    UpdateValidationExecutionRequest,
)
from app.modules.quality.service.validation import (
    create_validation,
    delete_validation,
    get_validation_detail,
    get_validation_execution_list,
    update_validation,
    update_validation_execution,
)
from tests.modules.quality.validation_migration import reset_validation_records_table


@pytest.fixture(autouse=True)
async def _prepare_validation_records_table(db_session: AsyncSession):
    await reset_validation_records_table(db_session)

    yield

    await reset_validation_records_table(db_session)


@pytest.mark.anyio
async def test_create_validation_service_returns_validation_type(
    db_session: AsyncSession,
) -> None:
    created = await create_validation(
        db_session,
        CreateValidationRequest(
            validation_type="cleaning_validation",
            record_code="VAL-2026-201",
            title="洁净区清洁验证",
        ),
        "system",
    )

    assert created["record_code"] == "VAL-2026-201"
    assert created["validation_type"] == "cleaning_validation"

    execution_rows = await get_validation_execution_list(
        db_session,
        validation_type="cleaning_validation",
        page=1,
        page_size=20,
    )
    assert execution_rows["total"] == 1
    assert execution_rows["items"][0]["master_validation_id"] == created["id"]
    assert execution_rows["items"][0]["title"] == "洁净区清洁验证"


@pytest.mark.anyio
async def test_create_validation_service_rejects_duplicate_record_code(
    db_session: AsyncSession,
) -> None:
    await create_validation(
        db_session,
        CreateValidationRequest(
            validation_type="process_validation",
            record_code="VAL-2026-202",
            title="首次工艺验证",
        ),
        "system",
    )

    with pytest.raises(ValueError, match="验证记录编号已存在"):
        await create_validation(
            db_session,
            CreateValidationRequest(
                validation_type="process_validation",
                record_code="VAL-2026-202",
                title="重复编号工艺验证",
            ),
            "system",
        )


@pytest.mark.anyio
async def test_update_validation_service_persists_changes(
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="equipment_qualification",
        record_code="VAL-2026-203",
        title="原始设备确认",
        status="draft",
    )
    db_session.add(record)
    await db_session.commit()

    updated = await update_validation(
        db_session,
        record.id,
        UpdateValidationRequest(
            validation_type="process_validation",
            title="更新后的工艺验证",
            status="approved",
        ),
        "system",
    )

    assert updated["validation_type"] == "process_validation"
    assert updated["title"] == "更新后的工艺验证"
    assert updated["status"] == "approved"

    detail = await get_validation_detail(db_session, record.id)
    assert detail.validation_type == "process_validation"

    process_rows = await get_validation_execution_list(
        db_session,
        validation_type="process_validation",
        page=1,
        page_size=20,
    )
    equipment_rows = await get_validation_execution_list(
        db_session,
        validation_type="equipment_qualification",
        page=1,
        page_size=20,
    )
    assert process_rows["total"] == 1
    assert process_rows["items"][0]["master_validation_id"] == record.id
    assert process_rows["items"][0]["title"] == "更新后的工艺验证"
    assert equipment_rows["total"] == 0


@pytest.mark.anyio
async def test_update_validation_execution_service_updates_child_fields(
    db_session: AsyncSession,
) -> None:
    created = await create_validation(
        db_session,
        CreateValidationRequest(
            validation_type="other_validation",
            record_code="VAL-2026-205",
            title="其他验证跟踪",
            department="质量部",
        ),
        "system",
    )

    updated_execution = await update_validation_execution(
        db_session,
        validation_type="other_validation",
        record_id=created["id"],
        data=UpdateValidationExecutionRequest(
            plan_name="年度再验证方案",
            plan_code="PLAN-205",
            report_no="REPORT-205",
            revalidation_cycle_years=2,
        ),
        user_id="system",
    )
    assert updated_execution["plan_name"] == "年度再验证方案"
    assert updated_execution["plan_code"] == "PLAN-205"
    assert updated_execution["report_no"] == "REPORT-205"
    assert updated_execution["revalidation_cycle_years"] == 2


@pytest.mark.anyio
async def test_delete_validation_service_soft_deletes_record(
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="equipment_qualification",
        record_code="VAL-2026-204",
        title="待删除验证",
    )
    db_session.add(record)
    await db_session.commit()

    result = await delete_validation(db_session, record.id)
    assert result["success"] is True

    execution_rows = await get_validation_execution_list(
        db_session,
        validation_type="equipment_qualification",
        page=1,
        page_size=20,
    )
    assert execution_rows["total"] == 0

    with pytest.raises(ValueError, match="not found"):
        await get_validation_detail(db_session, record.id)
