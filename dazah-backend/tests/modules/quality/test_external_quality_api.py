"""Integration tests for the platform-owned external quality slice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.external_quality import (
    ComplaintRecord,
    ProductQualityRecord,
    ProductQualityStandardItem,
    ReturnRecallRecord,
    Supplier,
    SupplierQualification,
)
from app.modules.quality.service import (
    external_quality_feishu,
    quality_feishu_settings,
)
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
    QualityFeishuRuntimeConfig,
)

_MODELS = (
    ProductQualityStandardItem,
    ProductQualityRecord,
    ReturnRecallRecord,
    ComplaintRecord,
    SupplierQualification,
    Supplier,
)


@pytest.fixture(autouse=True)
async def _clean_external_quality_records(
    db_session: AsyncSession,
) -> AsyncIterator[Any]:
    for model in _MODELS:
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    for model in _MODELS:
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_supplier_qualification_is_soft_deleted_with_supplier(
    client: AsyncClient,
) -> None:
    supplier = await client.post(
        "/api/v1/quality/suppliers",
        json={"supplier_code": "SUP-001", "name": "华东原料有限公司"},
    )
    assert supplier.status_code == 200
    supplier_id = supplier.json()["data"]["id"]

    qualification = await client.post(
        f"/api/v1/quality/suppliers/{supplier_id}/qualifications",
        json={
            "qualification_code": "QUAL-001",
            "qualification_name": "GMP符合性证明",
            "expiry_date": date(2027, 7, 13).isoformat(),
            "status": "valid",
        },
    )
    assert qualification.status_code == 200

    deleted = await client.delete(f"/api/v1/quality/suppliers/{supplier_id}")
    assert deleted.status_code == 200

    remaining = await client.get(
        f"/api/v1/quality/suppliers/{supplier_id}/qualifications"
    )
    assert remaining.status_code == 404


@pytest.mark.anyio
async def test_complaint_requires_investigation_and_response_before_close(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/quality/complaints",
        json={
            "complaint_code": "CMP-202607-001",
            "title": "客户反馈包装标签不清晰",
            "customer_name": "示例客户",
        },
    )
    assert created.status_code == 200
    complaint_id = created.json()["data"]["id"]

    assert (
        await client.post(f"/api/v1/quality/complaints/{complaint_id}/close")
    ).status_code == 400
    started = await client.post(
        f"/api/v1/quality/complaints/{complaint_id}/start-investigation"
    )
    assert started.json()["data"]["status"] == "investigating"
    responded = await client.post(
        f"/api/v1/quality/complaints/{complaint_id}/respond",
        json={
            "investigation_result": "印刷参数偏差",
            "response_content": "已完成更换与复核",
        },
    )
    assert responded.json()["data"]["status"] == "responded"
    closed = await client.post(f"/api/v1/quality/complaints/{complaint_id}/close")
    assert closed.json()["data"]["status"] == "closed"
    assert closed.json()["data"]["closed_at"] is not None


@pytest.mark.anyio
async def test_return_recall_and_product_quality_have_controlled_completion_paths(
    client: AsyncClient,
) -> None:
    returned = await client.post(
        "/api/v1/quality/return-recalls",
        json={
            "record_code": "RET-202607-001",
            "record_type": "return",
            "title": "客户退货处理",
            "product_name": "阿卡波糖",
        },
    )
    return_id = returned.json()["data"]["id"]
    assert (
        await client.post(
            f"/api/v1/quality/return-recalls/{return_id}/complete",
            json={"disposition": "销毁"},
        )
    ).status_code == 400
    assert (
        await client.post(
            f"/api/v1/quality/return-recalls/{return_id}/start-assessment"
        )
    ).json()["data"]["status"] == "assessing"
    assert (
        await client.post(
            f"/api/v1/quality/return-recalls/{return_id}/start-processing", json={}
        )
    ).json()["data"]["status"] == "processing"
    completed = await client.post(
        f"/api/v1/quality/return-recalls/{return_id}/complete",
        json={"disposition": "销毁"},
    )
    assert completed.json()["data"]["status"] == "completed"

    standard = await client.post(
        "/api/v1/quality/product-quality",
        json={
            "record_code": "STD-202607-001",
            "record_type": "customer_standard",
            "title": "客户质量标准",
            "product_name": "阿卡波糖",
            "quality_standard": "符合注册标准",
        },
    )
    standard_id = standard.json()["data"]["id"]
    item = await client.post(
        f"/api/v1/quality/product-quality/{standard_id}/standard-items",
        json={
            "display_order": 1,
            "item_name": "外包装",
            "requirement": "标签清晰、密封完好",
        },
    )
    assert item.status_code == 200
    duplicate_item = await client.post(
        f"/api/v1/quality/product-quality/{standard_id}/standard-items",
        json={"display_order": 1, "item_name": "运输", "requirement": "避光运输"},
    )
    assert duplicate_item.status_code == 409
    assert (
        await client.post(
            f"/api/v1/quality/product-quality/{standard_id}/complete",
            json={"conclusion": "标准已复核", "reviewer": "QA"},
        )
    ).json()["data"]["status"] == "completed"
    approved = await client.post(
        f"/api/v1/quality/product-quality/{standard_id}/approve"
    )
    assert approved.json()["data"]["status"] == "approved"


@pytest.mark.anyio
async def test_external_quality_entities_are_push_only_and_supplier_can_be_pushed(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_entity_codes = {
        "supplier_ledger",
        "supplier_qualification",
        "complaint_ledger",
        "return_recall_ledger",
        "product_quality_ledger",
        "product_quality_standard_item",
    }
    defaults = quality_feishu_settings._build_default_entity_items()
    external_defaults = {
        item.entity_code: item
        for item in defaults
        if item.entity_code in expected_entity_codes
    }
    assert set(external_defaults) == expected_entity_codes
    assert all(item.enable_push_to_feishu for item in external_defaults.values())
    assert all(not item.enable_pull_from_feishu for item in external_defaults.values())

    created = await client.post(
        "/api/v1/quality/suppliers",
        json={"supplier_code": "SUP-SYNC-001", "name": "同步测试供应商"},
    )
    supplier_id = created.json()["data"]["id"]
    runtime = QualityFeishuRuntimeConfig(
        app_id="cli_test",
        app_secret="secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "supplier_ledger": QualityFeishuEntityRuntimeConfig(
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
        external_quality_feishu.feishu_sync,  # type: ignore[attr-defined]
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )
    upsert: Any = AsyncMock(return_value=("rec_supplier_001", "tbl_test"))
    monkeypatch.setattr(external_quality_feishu.feishu_sync, "_upsert_record", upsert)  # type: ignore[attr-defined]

    pushed = await client.post(
        f"/api/v1/quality/suppliers/{supplier_id}/sync-to-feishu"
    )
    assert pushed.status_code == 200
    assert pushed.json()["data"]["entity_code"] == "supplier_ledger"
    upsert.assert_awaited_once()
