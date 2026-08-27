"""Product Quality Feishu pages service.

Operates directly on Feishu Bitable tables for product quality customer standards.
One table per product, all sharing the same field structure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import (
    quality_feishu_sync as feishu_sync_service,
)
from app.modules.quality.service.quality_feishu_pages import (
    _build_page_result,
    _contains_text,
    _create_entity_record,
    _delete_entity_record,
    _resolve_runtime_entity,
    _search_entity_records,
    _update_entity_record,
)
from app.modules.quality.service.quality_feishu_settings import (
    ensure_quality_feishu_entity_settings,
)

logger = logging.getLogger(__name__)


async def _ensure_entity(db: AsyncSession, entity_code: str) -> None:
    """Ensure the entity code is seeded in the database before use."""
    await ensure_quality_feishu_entity_settings(db)


# ============ Product Quality Standard Record ============


def _map_product_quality_record(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    fields = record.get("fields") or {}
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    modified_at = feishu_sync_service._get_record_modified_at(record)
    created_at = (
        parse_datetime(record.get("created_time")) or modified_at or datetime.now(UTC)
    )

    attachments_raw = field_value(entity, fields, "发货时包装照片")
    attachment_list: list[dict[str, Any]] = []
    if isinstance(attachments_raw, list):
        attachment_list = [
            {
                "name": a.get("name", ""),
                "url": a.get("url", ""),
                "type": a.get("type", ""),
                "size": a.get("size", 0),
            }
            for a in attachments_raw
            if isinstance(a, dict)
        ]

    return {
        "record_id": str(record.get("record_id") or ""),
        "serial_number": normalize_text(field_value(entity, fields, "序号")),
        "customer_name": normalize_text(field_value(entity, fields, "客户名称")),
        "quality_standard": normalize_text(field_value(entity, fields, "质量标准")),
        "shipping_trend_url": normalize_text(
            field_value(entity, fields, "历史发货趋势")
        ),
        "special_requirements": normalize_text(field_value(entity, fields, "特殊要求")),
        "packaging_requirements": normalize_text(
            field_value(entity, fields, "包装要求")
        ),
        "label_requirements": normalize_text(field_value(entity, fields, "标签要求")),
        "packaging_photos": attachment_list,
        "pallet_requirements": normalize_text(
            field_value(entity, fields, "发货打托要求")
        ),
        "target_market": normalize_text(field_value(entity, fields, "目标市场")),
        "registration_status": normalize_text(field_value(entity, fields, "注册情况")),
        "other_notes": normalize_text(field_value(entity, fields, "其他注意事项")),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_product_quality_records(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    await _ensure_entity(db, entity_code)
    _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    records = await _search_entity_records(db, entity_code)
    items = [_map_product_quality_record(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if _contains_text(item.get("customer_name"), kw)
            or _contains_text(item.get("quality_standard"), kw)
            or _contains_text(item.get("special_requirements"), kw)
            or _contains_text(item.get("target_market"), kw)
        ]

    items.sort(
        key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_product_quality_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> dict[str, Any] | None:
    await _ensure_entity(db, entity_code)
    _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    records = await _search_entity_records(db, entity_code)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_product_quality_record(record, entity)
    return None


async def create_product_quality_record(
    db: AsyncSession,
    entity_code: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    await _ensure_entity(db, entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
    fields: dict[str, Any] = {}
    _set_if_present(fields, entity, "客户名称", data.get("customer_name"))
    _set_if_present(fields, entity, "质量标准", data.get("quality_standard"))
    _set_if_present(fields, entity, "历史发货趋势", data.get("shipping_trend_url"))
    _set_if_present(fields, entity, "特殊要求", data.get("special_requirements"))
    _set_if_present(fields, entity, "包装要求", data.get("packaging_requirements"))
    _set_if_present(fields, entity, "标签要求", data.get("label_requirements"))
    _set_if_present(fields, entity, "发货打托要求", data.get("pallet_requirements"))
    _set_if_present(fields, entity, "目标市场", data.get("target_market"))
    _set_if_present(fields, entity, "注册情况", data.get("registration_status"))
    _set_if_present(fields, entity, "其他注意事项", data.get("other_notes"))

    result = await _create_entity_record(db, entity_code, fields)
    record_id = result["record_id"]

    # Fetch full record from Feishu to return complete data
    from app.platform.integrations.feishu.bitable import BitableClient

    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    feishu_record = await client.get_record(
        feishu_sync_service._require_table_id(entity), record_id
    )
    if feishu_record:
        return _map_product_quality_record(feishu_record, entity)
    return {"record_id": record_id}


async def update_product_quality_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    await _ensure_entity(db, entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
    fields: dict[str, Any] = {}
    _set_if_present(fields, entity, "客户名称", data.get("customer_name"))
    _set_if_present(fields, entity, "质量标准", data.get("quality_standard"))
    _set_if_present(fields, entity, "历史发货趋势", data.get("shipping_trend_url"))
    _set_if_present(fields, entity, "特殊要求", data.get("special_requirements"))
    _set_if_present(fields, entity, "包装要求", data.get("packaging_requirements"))
    _set_if_present(fields, entity, "标签要求", data.get("label_requirements"))
    _set_if_present(fields, entity, "发货打托要求", data.get("pallet_requirements"))
    _set_if_present(fields, entity, "目标市场", data.get("target_market"))
    _set_if_present(fields, entity, "注册情况", data.get("registration_status"))
    _set_if_present(fields, entity, "其他注意事项", data.get("other_notes"))

    await _update_entity_record(db, entity_code, record_id, fields)

    # Fetch full record from Feishu to return complete data
    from app.platform.integrations.feishu.bitable import BitableClient

    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    feishu_record = await client.get_record(
        feishu_sync_service._require_table_id(entity), record_id
    )
    if feishu_record:
        return _map_product_quality_record(feishu_record, entity)
    return {"record_id": record_id}


async def delete_product_quality_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> None:
    await _ensure_entity(db, entity_code)
    await _delete_entity_record(db, entity_code, record_id)


async def pull_product_quality_records(
    db: AsyncSession,
    entity_code: str,
) -> dict[str, int]:
    """Pull product quality records from Feishu. Returns {synced, failed}."""
    await _ensure_entity(db, entity_code)
    try:
        records = await _search_entity_records(db, entity_code)
        return {"synced": len(records), "failed": 0}
    except Exception:
        return {"synced": 0, "failed": 0}


# ============ helpers ============

# Field label mapping: Chinese label → system field name
# Used for both read and write to ensure consistency
_FIELD_LABEL_TO_SYSTEM = {
    "客户名称": "customer_name",
    "质量标准": "quality_standard",
    "历史发货趋势": "shipping_trend_url",
    "特殊要求": "special_requirements",
    "包装要求": "packaging_requirements",
    "标签要求": "label_requirements",
    "发货打托要求": "pallet_requirements",
    "目标市场": "target_market",
    "注册情况": "registration_status",
    "其他注意事项": "other_notes",
}


def _set_if_present(
    fields: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
    field_label: str,
    value: Any,
) -> None:
    """Set a field value using the system field name as the key.

    The key must match what _get_mapped_field_value expects during read.
    Since field_mappings is empty for product quality entities, we use
    the system field name directly as both the dict key and the feishu field name.
    """
    if value is None:
        return
    # Use system field name as the key (consistent with read path)
    system_field = _FIELD_LABEL_TO_SYSTEM.get(field_label, field_label)
    fields[system_field] = value
