"""Integration tests for the platform-owned OOS/OOT quality slice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.oos_oot import (
    OosOotRecord,
    OotLimitItem,
    OotLimitProduct,
)
from app.modules.quality.service import oos_oot_feishu, quality_feishu_settings
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
    QualityFeishuRuntimeConfig,
)


@pytest.fixture(autouse=True)
async def _clean_oos_oot_records(db_session: AsyncSession) -> AsyncIterator[Any]:
    for model in (OotLimitItem, OotLimitProduct, OosOotRecord):
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    for model in (OotLimitItem, OotLimitProduct, OosOotRecord):
        await db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_oos_oot_record_requires_investigation_before_close(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/quality/oos-oot/records",
        json={
            "record_code": "OOS-202607-001",
            "record_type": "OOS",
            "title": "含量超出标准",
            "product_name": "阿卡波糖",
            "batch_no": "B-202607-01",
            "test_item": "含量",
            "discovered_date": date(2026, 7, 13).isoformat(),
        },
    )
    assert created.status_code == 200
    record_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "open"

    close_before_investigation = await client.post(
        f"/api/v1/quality/oos-oot/records/{record_id}/close",
        json={"investigation_result": "尚未启动调查"},
    )
    assert close_before_investigation.status_code == 400

    started = await client.post(
        f"/api/v1/quality/oos-oot/records/{record_id}/start-investigation"
    )
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "investigating"

    closed = await client.post(
        f"/api/v1/quality/oos-oot/records/{record_id}/close",
        json={
            "investigation_result": "复测确认方法偏差，已完成纠正。",
            "corrective_actions": "修订操作规程并培训。",
        },
    )
    assert closed.status_code == 200
    assert closed.json()["data"]["status"] == "closed"
    assert closed.json()["data"]["closed_at"] is not None


@pytest.mark.anyio
async def test_oot_limit_item_is_bound_by_service_not_database_foreign_key(
    client: AsyncClient,
) -> None:
    product = await client.post(
        "/api/v1/quality/oos-oot/oot-limits/products",
        json={
            "product_code": "ACB-001",
            "product_name": "阿卡波糖",
            "document_no": "QCS-001",
        },
    )
    assert product.status_code == 200
    product_id = product.json()["data"]["id"]

    item = await client.post(
        f"/api/v1/quality/oos-oot/oot-limits/products/{product_id}/items",
        json={
            "display_order": 1,
            "item_group": "有关物质",
            "item_name": "总杂质",
            "specification": "≤1.00%",
            "oot_limit": "连续三批上升且接近 0.80% 时预警",
        },
    )
    assert item.status_code == 200
    assert item.json()["data"]["product_id"] == product_id

    duplicate_order = await client.post(
        f"/api/v1/quality/oos-oot/oot-limits/products/{product_id}/items",
        json={
            "display_order": 1,
            "item_name": "单个杂质",
            "oot_limit": "超过均值两倍标准差时预警",
        },
    )
    assert duplicate_order.status_code == 409

    missing_product = await client.post(
        "/api/v1/quality/oos-oot/oot-limits/products/"
        "00000000-0000-0000-0000-000000000000/items",
        json={"display_order": 1, "item_name": "含量", "oot_limit": "接近下限时预警"},
    )
    assert missing_product.status_code == 404


@pytest.mark.anyio
async def test_oos_oot_feishu_entities_are_push_only_and_single_record_can_be_pushed(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_entity_codes = {
        "oos_ledger",
        "oot_ledger",
        "oot_limit_product",
        "oot_limit_item",
    }
    defaults = quality_feishu_settings._build_default_entity_items()
    oos_oot_defaults = {
        item.entity_code: item
        for item in defaults
        if item.entity_code in expected_entity_codes
    }
    assert set(oos_oot_defaults) == expected_entity_codes
    assert all(item.enable_push_to_feishu for item in oos_oot_defaults.values())
    assert all(not item.enable_pull_from_feishu for item in oos_oot_defaults.values())

    created = await client.post(
        "/api/v1/quality/oos-oot/records",
        json={
            "record_code": "OOT-202607-001",
            "record_type": "OOT",
            "title": "杂质趋势上升",
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
            "oot_ledger": QualityFeishuEntityRuntimeConfig(
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
        oos_oot_feishu.feishu_sync,  # type: ignore[attr-defined]
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )
    upsert: Any = AsyncMock(return_value=("rec_oot_001", "tbl_test"))
    monkeypatch.setattr(oos_oot_feishu.feishu_sync, "_upsert_record", upsert)  # type: ignore[attr-defined]

    pushed = await client.post(
        f"/api/v1/quality/oos-oot/records/{record_id}/sync-to-feishu"
    )
    assert pushed.status_code == 200
    assert pushed.json()["data"]["entity_code"] == "oot_ledger"
    assert pushed.json()["data"]["record_id"] == "rec_oot_001"
    upsert.assert_awaited_once()
