from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord
from app.modules.quality.repository.validation import (
    create_validation,
    delete_validation,
    exists_by_record_code,
    get_validation_by_id,
    get_validations,
    update_validation,
)
from tests.modules.quality.validation_migration import reset_validation_records_table


@pytest.fixture(autouse=True)
async def _prepare_validation_records_table(db_session: AsyncSession):
    await reset_validation_records_table(db_session)

    yield

    await reset_validation_records_table(db_session)


@pytest.mark.anyio
async def test_get_validations_filters_by_type_and_keyword(
    db_session: AsyncSession,
) -> None:
    keep = ValidationRecord(
        id=uuid.uuid4(),
        record_type="process_validation",
        record_code="VAL-2026-101",
        title="工艺再验证",
        department="生产部",
    )
    skip = ValidationRecord(
        id=uuid.uuid4(),
        record_type="cleaning_validation",
        record_code="VAL-2026-102",
        title="清洁验证",
        department="质量部",
    )
    db_session.add_all([keep, skip])
    await db_session.commit()

    items, total = await get_validations(
        db_session,
        validation_type="process_validation",
        keyword="再验证",
        page=1,
        page_size=20,
    )

    assert total == 1
    assert items[0].record_code == "VAL-2026-101"


@pytest.mark.anyio
async def test_validation_repository_create_update_and_soft_delete(
    db_session: AsyncSession,
) -> None:
    created = await create_validation(
        db_session,
        {
            "record_type": "equipment_qualification",
            "record_code": "VAL-2026-103",
            "title": "制水系统 IQ",
            "planned_end_date": date(2026, 7, 10),
        },
    )
    await db_session.commit()

    assert await exists_by_record_code(db_session, "VAL-2026-103") is True

    updated = await update_validation(
        db_session,
        created,
        {
            "record_type": "process_validation",
            "title": "制水系统再验证",
            "planned_end_date": date(2026, 7, 15),
        },
    )
    await db_session.commit()

    found = await get_validation_by_id(db_session, created.id)
    assert found is not None
    assert updated.record_type == "process_validation"
    assert found.title == "制水系统再验证"
    assert found.planned_end_date == date(2026, 7, 15)

    await delete_validation(db_session, created)
    await db_session.commit()

    assert await get_validation_by_id(db_session, created.id) is None
    assert await exists_by_record_code(db_session, "VAL-2026-103") is False


@pytest.mark.anyio
async def test_exists_by_record_code_supports_exclude_id(
    db_session: AsyncSession,
) -> None:
    created = await create_validation(
        db_session,
        {
            "record_type": "cleaning_validation",
            "record_code": "VAL-2026-104",
            "title": "设备清洁验证",
        },
    )
    await db_session.commit()

    assert await exists_by_record_code(db_session, "VAL-2026-104") is True
    assert (
        await exists_by_record_code(
            db_session,
            "VAL-2026-104",
            exclude_id=created.id,
        )
        is False
    )
