"""Integration tests for inspection Feishu mapping and local trend analysis."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.inspection import (
    FinishedProductInspection,
    InspectionRecord,
    LiquidMaterialInspection,
    SolidMaterialInspection,
)
from app.modules.quality.service import inspection_feishu, quality_feishu_settings
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
    QualityFeishuRuntimeConfig,
)

_MEASUREMENT_MODELS = (
    LiquidMaterialInspection,
    SolidMaterialInspection,
    FinishedProductInspection,
    InspectionRecord,
)


@pytest.fixture(autouse=True)
async def _clean_measurement_records(db_session: AsyncSession) -> AsyncIterator[Any]:
    for model in _MEASUREMENT_MODELS:
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    for model in _MEASUREMENT_MODELS:
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_finished_product_trend_uses_local_records_and_flags_spec_limit(
    client: AsyncClient,
) -> None:
    for inspection_no, batch_no, result in (
        ("FP-TREND-001", "B-001", "0.80%"),
        ("FP-TREND-002", "B-002", "0.90%"),
        ("FP-TREND-003", "B-003", "1.20%"),
    ):
        response = await client.post(
            "/api/v1/quality/finished-product-inspections",
            json={
                "inspection_no": inspection_no,
                "product_name": "阿卡波糖",
                "batch_no": batch_no,
                "inspection_item": "总杂质",
                "specification": "≤1.00%",
                "test_result": result,
                "conclusion": "合格",
                "inspection_date": date(2026, 7, int(batch_no[-1])).isoformat(),
            },
        )
        assert response.status_code == 200

    trend = await client.get(
        "/api/v1/quality/inspection-trends",
        params={
            "resource_code": "finished_product_inspections",
            "subject": "阿卡波糖",
            "inspection_item": "总杂质",
        },
    )

    assert trend.status_code == 200
    payload = trend.json()
    assert [point["value"] for point in payload["points"]] == [0.8, 0.9, 1.2]
    assert payload["summary"]["sample_count"] == 3
    assert payload["summary"]["alert_count"] == 1
    assert payload["alerts"][0]["alert_type"] == "specification_limit"


@pytest.mark.anyio
async def test_inspection_dashboard_returns_resource_summary_and_latest_records(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/quality/finished-product-inspections",
        json={
            "inspection_no": "FP-DASH-001",
            "product_name": "阿卡波糖",
            "batch_no": "B-DASH-001",
            "inspection_item": "含量",
            "conclusion": "合格",
        },
    )
    assert created.status_code == 200

    response = await client.get("/api/v1/quality/inspection-dashboard")

    assert response.status_code == 200
    payload = response.json()
    finished_summary = next(
        item
        for item in payload["resource_summaries"]
        if item["resource_code"] == "finished_product_inspections"
    )
    assert finished_summary["total"] == 1
    assert finished_summary["qualified"] == 1
    assert payload["latest_records"][0]["inspection_no"] == "FP-DASH-001"


@pytest.mark.anyio
async def test_single_inspection_record_can_be_explicitly_pushed_to_feishu(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await client.post(
        "/api/v1/quality/finished-product-inspections",
        json={
            "inspection_no": "FP-SYNC-001",
            "product_name": "阿卡波糖",
            "batch_no": "B-SYNC-001",
            "inspection_item": "含量",
            "conclusion": "合格",
        },
    )
    assert created.status_code == 200
    record_id = created.json()["data"]["id"]

    runtime = QualityFeishuRuntimeConfig(
        app_id="cli_test",
        app_secret="secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "inspection_finished_product": QualityFeishuEntityRuntimeConfig(
                app_token="basc_test",
                table_id="tbl_test",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=False,
                field_mappings={},
            )
        },
    )
    monkeypatch.setattr(
        inspection_feishu.feishu_sync,  # type: ignore[attr-defined]
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )
    upsert: Any = AsyncMock(return_value=("rec_finished_001", "tbl_test"))
    monkeypatch.setattr(inspection_feishu.feishu_sync, "_upsert_record", upsert)  # type: ignore[attr-defined]

    response = await client.post(
        "/api/v1/quality/inspection-resources/"
        f"finished_product_inspections/{record_id}/sync-to-feishu"
    )

    assert response.status_code == 200
    assert response.json()["entity_code"] == "inspection_finished_product"
    assert response.json()["record_id"] == "rec_finished_001"
    upsert.assert_awaited_once()


@pytest.mark.anyio
async def test_inspection_feishu_entities_default_to_push_only(
    client: AsyncClient,
) -> None:
    expected_entity_codes = {
        "inspection_general",
        "inspection_lab_item",
        "inspection_lab_instrument",
        "inspection_finished_product",
        "inspection_solid_material",
        "inspection_liquid_material",
    }
    defaults = quality_feishu_settings._build_default_entity_items()
    inspection_defaults = {
        item.entity_code: item
        for item in defaults
        if item.entity_code in expected_entity_codes
    }

    assert set(inspection_defaults) == expected_entity_codes
    assert all(item.enable_push_to_feishu for item in inspection_defaults.values())
    assert all(
        not item.enable_pull_from_feishu for item in inspection_defaults.values()
    )

    response = await client.get("/api/v1/quality/feishu-settings/entities")

    assert response.status_code == 200
    configured_items = {item["entity_code"]: item for item in response.json()}
    assert set(configured_items) >= expected_entity_codes
    assert all(
        not configured_items[entity_code]["enable_pull_from_feishu"]
        for entity_code in expected_entity_codes
    )
