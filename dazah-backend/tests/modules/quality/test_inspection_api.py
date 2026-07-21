"""Integration tests for the quality inspection foundation API."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.inspection import (
    FinishedProductInspection,
    InspectionRecord,
    LabInstrument,
    LabItem,
    LiquidMaterialInspection,
    SolidMaterialInspection,
)

_MODELS = (
    LiquidMaterialInspection,
    SolidMaterialInspection,
    FinishedProductInspection,
    InspectionRecord,
    LabInstrument,
    LabItem,
)
_TABLES = (
    "quality.lab_items",
    "quality.lab_instruments",
    "quality.inspection_records",
    "quality.finished_product_inspections",
    "quality.solid_material_inspections",
    "quality.liquid_material_inspections",
)


@pytest.fixture(autouse=True)
async def _clean_inspection_tables(db_session: AsyncSession) -> None:
    missing_tables = [
        table_name
        for table_name in _TABLES
        if (
            await db_session.execute(text(f"SELECT to_regclass('{table_name}')"))
        ).scalar_one()
        != table_name
    ]
    if missing_tables:
        pytest.fail(
            "Inspection foundation migration is not applied to the test database: "
            + ", ".join(missing_tables)
        )

    for model in _MODELS:
        await db_session.execute(model.__table__.delete())
    await db_session.commit()
    yield
    for model in _MODELS:
        await db_session.execute(model.__table__.delete())
    await db_session.commit()


@pytest.mark.anyio
async def test_inspection_foundation_tables_exist(db_session: AsyncSession) -> None:
    tables = [
        (
            await db_session.execute(text(f"SELECT to_regclass('{table_name}')"))
        ).scalar_one()
        for table_name in _TABLES
    ]

    assert tables == list(_TABLES)

    foreign_key_count = (
        await db_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE contype = 'f'
                  AND connamespace = 'quality'::regnamespace
                  AND conrelid IN (
                    SELECT c.oid
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'quality'
                      AND c.relname = ANY(:table_names)
                  )
                """
            ),
            {"table_names": [table_name.split(".", 1)[1] for table_name in _TABLES]},
        )
    ).scalar_one()
    assert foreign_key_count == 0


@pytest.mark.anyio
async def test_inspection_record_crud_filter_duplicate_and_soft_delete(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/quality/inspections",
        json={
            "inspection_no": "QI-2026-001",
            "product_name": "阿卡波糖",
            "batch_no": "B-001",
            "inspection_type": "成品检验",
            "inspection_item": "含量",
            "conclusion": "合格",
            "inspection_date": "2026-07-13",
            "department": "质量部",
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["inspection_no"] == "QI-2026-001"

    duplicate_response = await client.post(
        "/api/v1/quality/inspections",
        json={"inspection_no": "QI-2026-001"},
    )
    assert duplicate_response.status_code == 409

    list_response = await client.get(
        "/api/v1/quality/inspections",
        params={
            "inspection_type": "成品检验",
            "keyword": "阿卡",
            "page": 1,
            "page_size": 20,
        },
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    update_response = await client.put(
        f"/api/v1/quality/inspections/{created['id']}",
        json={"conclusion": "不合格", "inspection_date": date(2026, 7, 14).isoformat()},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["conclusion"] == "不合格"

    delete_response = await client.delete(
        f"/api/v1/quality/inspections/{created['id']}"
    )
    assert delete_response.status_code == 200

    deleted_detail_response = await client.get(
        f"/api/v1/quality/inspections/{created['id']}"
    )
    assert deleted_detail_response.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload", "expected_field", "expected_value"),
    [
        (
            "/api/v1/quality/lab-items",
            {"name": "乙腈", "quantity": 2, "unit": "瓶", "status": "normal"},
            "name",
            "乙腈",
        ),
        (
            "/api/v1/quality/lab-instruments",
            {"name": "液相色谱仪", "serial_no": "HPLC-001", "status": "normal"},
            "serial_no",
            "HPLC-001",
        ),
        (
            "/api/v1/quality/finished-product-inspections",
            {
                "inspection_no": "FP-001",
                "product_name": "阿卡波糖",
                "conclusion": "合格",
            },
            "inspection_no",
            "FP-001",
        ),
        (
            "/api/v1/quality/solid-material-inspections",
            {"inspection_no": "SM-001", "material_name": "淀粉", "conclusion": "合格"},
            "material_name",
            "淀粉",
        ),
        (
            "/api/v1/quality/liquid-material-inspections",
            {"inspection_no": "LM-001", "material_name": "乙醇", "conclusion": "合格"},
            "material_name",
            "乙醇",
        ),
    ],
)
async def test_inspection_subresource_create_and_list(
    client: AsyncClient,
    path: str,
    payload: dict[str, object],
    expected_field: str,
    expected_value: str,
) -> None:
    create_response = await client.post(path, json=payload)
    assert create_response.status_code == 200
    assert create_response.json()["data"][expected_field] == expected_value

    list_response = await client.get(path, params={"page": 1, "page_size": 20})
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1
