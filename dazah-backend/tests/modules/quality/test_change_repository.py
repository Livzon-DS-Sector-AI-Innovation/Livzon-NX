from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.change_control import ChangeControl
from app.modules.quality.repository.quality_management import (
    create_change,
    delete_change,
    exists_by_change_code,
    get_change_by_code,
    get_change_by_id,
    get_changes,
    update_change,
)


@pytest.fixture(autouse=True)
async def _prepare_change_controls_table(db_session: AsyncSession):
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.quality_change_controls (
                serial_number VARCHAR(50),
                change_code VARCHAR(100) NOT NULL UNIQUE,
                applicant_department VARCHAR(100),
                change_object VARCHAR(255),
                change_content TEXT,
                change_level VARCHAR(50),
                application_date DATE,
                planned_approval_date DATE,
                execution_date DATE,
                closure_date DATE,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(text("DELETE FROM quality.quality_change_controls"))
    await db_session.commit()

    yield

    await db_session.execute(text("DELETE FROM quality.quality_change_controls"))
    await db_session.commit()


@pytest.mark.anyio
async def test_get_changes_filters_by_code_and_department(
    db_session: AsyncSession,
) -> None:
    keep = ChangeControl(
        id=uuid.uuid4(),
        serial_number="1",
        change_code="BG-2026-001",
        applicant_department="质量部",
        change_object="反应釜",
        change_content="更换搅拌电机",
        change_level="二级",
        application_date=date(2026, 6, 30),
        planned_approval_date=date(2026, 7, 1),
        execution_date=date(2026, 7, 5),
        closure_date=date(2026, 7, 10),
    )
    skip = ChangeControl(
        id=uuid.uuid4(),
        serial_number="2",
        change_code="BG-2026-002",
        applicant_department="生产部",
        change_object="灌装线",
        change_content="调整清场顺序",
        change_level="三级",
        application_date=date(2026, 6, 29),
    )
    db_session.add_all([keep, skip])
    await db_session.commit()

    items, total = await get_changes(
        db_session,
        change_code="BG-2026-001",
        applicant_department="质量部",
        page=1,
        page_size=20,
    )

    assert total == 1
    assert items[0].change_code == "BG-2026-001"
    assert items[0].applicant_department == "质量部"


@pytest.mark.anyio
async def test_get_change_by_code_returns_existing_row(
    db_session: AsyncSession,
) -> None:
    row = ChangeControl(
        id=uuid.uuid4(),
        serial_number="3",
        change_code="BG-2026-003",
        applicant_department="设备部",
        change_object="空调机组",
        change_content="更换过滤器",
        change_level="一级",
        application_date=date(2026, 7, 1),
    )
    db_session.add(row)
    await db_session.commit()

    found = await get_change_by_code(db_session, "BG-2026-003")

    assert found is not None
    assert found.change_object == "空调机组"


@pytest.mark.anyio
async def test_change_repository_create_update_and_soft_delete(
    db_session: AsyncSession,
) -> None:
    created = await create_change(
        db_session,
        {
            "serial_number": "4",
            "change_code": "BG-2026-004",
            "applicant_department": "工程部",
            "change_object": "纯化水系统",
            "change_content": "新增监测点位",
            "change_level": "一级",
            "application_date": date(2026, 7, 2),
        },
    )
    await db_session.commit()

    assert await exists_by_change_code(db_session, "BG-2026-004") is True

    updated = await update_change(
        db_session,
        created,
        {
            "change_object": "纯化水循环系统",
            "closure_date": date(2026, 7, 15),
        },
    )
    await db_session.commit()

    found = await get_change_by_id(db_session, created.id)
    assert found is not None
    assert updated.change_object == "纯化水循环系统"
    assert found.closure_date == date(2026, 7, 15)

    await delete_change(db_session, created)
    await db_session.commit()

    assert await get_change_by_id(db_session, created.id) is None
    assert await exists_by_change_code(db_session, "BG-2026-004") is False
