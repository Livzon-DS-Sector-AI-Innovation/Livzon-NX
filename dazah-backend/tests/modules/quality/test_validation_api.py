from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord
from tests.modules.quality.validation_migration import (
    assert_validation_migration_state,
    reset_validation_records_table,
)


@pytest.fixture(autouse=True)
async def _clean_validation_records(db_session: AsyncSession):
    await reset_validation_records_table(db_session)
    yield
    await reset_validation_records_table(db_session)


@pytest.mark.anyio
async def test_validation_migration_upgrade_tracks_target_revision(
    db_session: AsyncSession,
) -> None:
    await assert_validation_migration_state(db_session)


@pytest.mark.anyio
async def test_list_validations_api_returns_filtered_rows(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        ValidationRecord(
            id=uuid.uuid4(),
            record_type="equipment_qualification",
            record_code="VAL-2026-001",
            title="纯化水系统 IQ",
            status="pending",
            department="工程部",
            planned_end_date=date(2026, 7, 1),
        )
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/quality/validations",
        params={
            "record_code": "VAL-2026-001",
            "validation_type": "equipment_qualification",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["record_code"] == "VAL-2026-001"
    assert body["data"][0]["validation_type"] == "equipment_qualification"


@pytest.mark.anyio
async def test_create_validation_api_returns_created_row(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/quality/validations",
        json={
            "validation_type": "cleaning_validation",
            "record_code": "VAL-2026-002",
            "title": "多功能车间清洁验证",
            "status": "pending",
            "department": "质量部",
            "equipment_code": "EQ-001",
            "product_codes": ["MC", "LV"],
            "planned_end_date": "2026-07-03",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["record_code"] == "VAL-2026-002"
    assert body["data"]["validation_type"] == "cleaning_validation"

    execution_response = await client.get(
        "/api/v1/quality/validation-executions/cleaning_validation"
    )
    assert execution_response.status_code == 200
    execution_body = execution_response.json()
    assert execution_body["meta"]["total"] == 1
    assert execution_body["data"][0]["master_validation_id"] == body["data"]["id"]


@pytest.mark.anyio
async def test_get_validation_api_returns_detail(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="process_validation",
        record_code="VAL-2026-003",
        title="关键工艺参数再验证",
        status="completed",
        department="生产部",
        equipment_code="EQ-003",
        product_codes=["DR"],
        planned_end_date=date(2026, 7, 5),
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.get(f"/api/v1/quality/validations/{record.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == str(record.id)
    assert body["data"]["title"] == "关键工艺参数再验证"
    assert body["data"]["validation_type"] == "process_validation"


@pytest.mark.anyio
async def test_update_validation_api_updates_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="cleaning_validation",
        record_code="VAL-2026-004",
        title="原始清洁验证",
        status="draft",
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/quality/validations/{record.id}",
        json={
            "validation_type": "process_validation",
            "title": "更新后的工艺验证",
            "status": "completed",
            "department": "生产部",
            "equipment_code": "EQ-004",
            "planned_end_date": "2026-08-01",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["validation_type"] == "process_validation"
    assert body["data"]["title"] == "更新后的工艺验证"
    assert body["data"]["status"] == "completed"


@pytest.mark.anyio
async def test_delete_validation_api_soft_deletes_row(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = ValidationRecord(
        id=uuid.uuid4(),
        record_type="equipment_qualification",
        record_code="VAL-2026-005",
        title="待删除验证",
    )
    db_session.add(record)
    await db_session.commit()

    response = await client.delete(f"/api/v1/quality/validations/{record.id}")

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    detail_response = await client.get(f"/api/v1/quality/validations/{record.id}")
    assert detail_response.status_code == 404


@pytest.mark.anyio
async def test_update_validation_execution_api_updates_child_row(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/quality/validations",
        json={
            "validation_type": "other_validation",
            "record_code": "VAL-2026-006",
            "title": "其他验证执行",
            "department": "质量部",
        },
    )
    assert create_response.status_code == 200
    record_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/quality/validation-executions/other_validation/{record_id}",
        json={
            "plan_name": "2026年其他验证方案",
            "plan_code": "PLAN-006",
            "report_no": "REPORT-006",
            "revalidation_cycle_years": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["plan_name"] == "2026年其他验证方案"
    assert body["data"]["plan_code"] == "PLAN-006"
    assert body["data"]["report_no"] == "REPORT-006"
    assert body["data"]["revalidation_cycle_years"] == 3


@pytest.mark.anyio
async def test_batch_delete_validation_api_soft_deletes_rows(
    client: AsyncClient,
) -> None:
    create_ids = []
    for index in range(2):
        response = await client.post(
            "/api/v1/quality/validations",
            json={
                "validation_type": "equipment_qualification",
                "record_code": f"VAL-2026-B0{index + 1}",
                "title": f"批量删除验证{index + 1}",
            },
        )
        assert response.status_code == 200
        create_ids.append(response.json()["data"]["id"])

    response = await client.post(
        "/api/v1/quality/validations/batch-delete",
        json=create_ids,
    )

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == 2

    list_response = await client.get(
        "/api/v1/quality/validation-executions/equipment_qualification"
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 0
