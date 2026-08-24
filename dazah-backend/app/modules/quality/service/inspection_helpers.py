"""Inspection Feishu pages service helpers.

Shared utility functions for operating on Feishu Bitable tables
in quality inspection management.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.quality_feishu_pages import (
    _build_page_result,
    _resolve_runtime_entity,
    _search_entity_records,
)

logger = logging.getLogger(__name__)


# ── Helpers ──


def _normalize(value: Any) -> str | None:
    return feishu_sync_service._normalize_text(value)


def _parse_dt(value: Any) -> datetime | None:
    return feishu_sync_service._parse_feishu_datetime(value)


def _field(fields: dict[str, Any], entity: Any, name: str) -> Any:
    return feishu_sync_service._get_mapped_field_value(entity, fields, name)


def _dt_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _has_visible_field_value(item: dict[str, Any], field_names: list[str]) -> bool:
    """Skip Feishu placeholder rows whose business fields are entirely empty."""
    return any(_normalize(item.get(name)) for name in field_names)


async def _search_entity_records_with_fallback(
    db: AsyncSession,
    entity_code: str,
    *,
    field_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        return await _search_entity_records(db, entity_code, field_names=field_names)
    except Exception as exc:
        if not field_names:
            raise
        logger.warning(
            (
                "Feishu field-specific search failed for "
                "%s, retrying without field_names: %s"
            ),
            entity_code,
            exc,
        )
        return await _search_entity_records(db, entity_code, field_names=None)


def _base_map(
    record: dict[str, Any],
    entity: Any,
    field_names: list[str],
) -> dict[str, Any]:
    """Generic mapper: extracts each field_name from the Feishu record."""
    fields = record.get("fields") or {}
    modified_at = feishu_sync_service._get_record_modified_at(record)
    created_at = (
        _parse_dt(record.get("created_time")) or modified_at or datetime.now(UTC)
    )

    result: dict[str, Any] = {
        "record_id": str(record.get("record_id") or ""),
        "created_at": _dt_iso(created_at),
        "updated_at": _dt_iso(modified_at or created_at),
    }
    for name in field_names:
        result[name] = _normalize(_field(fields, entity, name))
    return result


def _get_link_record_ids(record: dict[str, Any], field_name: str) -> list[str]:
    fields = record.get("fields") or {}
    value = fields.get(field_name)
    if isinstance(value, dict):
        record_ids = value.get("link_record_ids")
        if isinstance(record_ids, list):
            return [str(item) for item in record_ids if item]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


async def _build_items_inventory_index(db: AsyncSession) -> dict[str, dict[str, Any]]:
    from app.modules.quality.service.inspection_items_equipment import ITEMS_FIELDS

    _, entity = await _resolve_runtime_entity(
        db, "qc_items_inventory", direction="pull"
    )
    records = await _search_entity_records(
        db, "qc_items_inventory", field_names=ITEMS_FIELDS
    )
    return {
        str(record.get("record_id") or ""): _base_map(record, entity, ITEMS_FIELDS)
        for record in records
        if record.get("record_id")
    }


def _fill_item_fields_from_inventory(
    item: dict[str, Any],
    record: dict[str, Any],
    inventory_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if item.get("物资名称") and item.get("规格型号"):
        return item

    link_record_ids = _get_link_record_ids(record, "物资名")
    if not link_record_ids:
        return item

    inventory_item = inventory_index.get(link_record_ids[0])
    if not inventory_item:
        return item

    if not item.get("物资名称"):
        item["物资名称"] = inventory_item.get("物资名称") or inventory_item.get(
            "物资名（规格）"
        )
    if not item.get("规格型号"):
        item["规格型号"] = inventory_item.get("规格型号")
    if "当前库存" in item and not item.get("当前库存"):
        item["当前库存"] = inventory_item.get("当前库存")
    return item


def _paginate_items(
    items: list[dict[str, Any]],
    page: int,
    page_size: int,
    field_names: list[str],
) -> dict[str, Any]:
    start = (page - 1) * page_size
    result = _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )
    result["fields"] = field_names
    return result


async def _list_item_records_with_inventory(
    db: AsyncSession,
    entity_code: str,
    field_names: list[str],
    keyword_fields: list[str],
    *,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
        records = await _search_entity_records_with_fallback(
            db,
            entity_code,
            field_names=[*field_names, "物资名"],
        )
        inventory_index = await _build_items_inventory_index(db)
        items = [
            _fill_item_fields_from_inventory(
                _base_map(record, entity, field_names),
                record,
                inventory_index,
            )
            for record in records
        ]
        items = [item for item in items if _has_visible_field_value(item, field_names)]
    except Exception as e:
        logger.warning("Feishu list failed for %s: %s", entity_code, e)
        return _build_page_result([], 0, page, page_size)

    if keyword and keyword_fields:
        kw = keyword.lower()
        items = [
            it
            for it in items
            if any(kw in (str(it.get(f) or "")).lower() for f in keyword_fields)
        ]

    if filters:
        for field_key, field_value in filters.items():
            if field_value:
                items = [
                    it for it in items if str(it.get(field_key) or "") == field_value
                ]

    return _paginate_items(items, page, page_size, field_names)


async def _get_item_record_with_inventory(
    db: AsyncSession,
    entity_code: str,
    field_names: list[str],
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    records = await _search_entity_records_with_fallback(
        db,
        entity_code,
        field_names=[*field_names, "物资名"],
    )
    inventory_index = await _build_items_inventory_index(db)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _fill_item_fields_from_inventory(
                _base_map(record, entity, field_names),
                record,
                inventory_index,
            )
    raise NotFoundException(resource="飞书记录", resource_id=str(record_id))


async def _list_feishu(
    db: AsyncSession,
    entity_code: str,
    field_names: list[str],
    keyword_fields: list[str] | None = None,
    keyword: str | None = None,
    filters: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Generic Feishu list: fetch, map, filter, sort, paginate."""
    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
        # NOTE: 不将 field_names 传给飞书 API
        # 搜索，因为硬编码的字段名可能与飞书表实际字段名
        # 存在细微差异（空格、标点等），导致飞书 API 返回空字段。
        # 改为获取全部字段，在 _base_map 中按 field_names 提取。
        records = await _search_entity_records_with_fallback(
            db,
            entity_code,
            field_names=None,
        )
        items = [_base_map(r, entity, field_names) for r in records]
        items = [item for item in items if _has_visible_field_value(item, field_names)]
    except Exception as e:
        logger.warning("Feishu list failed for %s: %s", entity_code, e)
        return _build_page_result([], 0, page, page_size)

    if keyword and keyword_fields:
        kw = keyword.lower()
        items = [
            it
            for it in items
            if any(kw in (str(it.get(f) or "")).lower() for f in keyword_fields)
        ]

    # Field-specific filters (exact match)
    if filters:
        for field_key, field_value in filters.items():
            if field_value:
                items = [
                    it for it in items if str(it.get(field_key) or "") == field_value
                ]

    items.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    start = (page - 1) * page_size
    result = _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )
    result["fields"] = field_names
    return result


async def _get_feishu_one(
    db: AsyncSession,
    entity_code: str,
    field_names: list[str],
    record_id: str,
) -> dict[str, Any]:
    """Generic Feishu get-one by record_id."""
    _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    records = await _search_entity_records_with_fallback(
        db, entity_code, field_names=field_names
    )
    for r in records:
        if str(r.get("record_id") or "") == record_id:
            return _base_map(r, entity, field_names)
    raise NotFoundException(resource="飞书记录", resource_id=str(record_id))


async def _pull_count(db: AsyncSession, entity_code: str) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        records = await _search_entity_records(db, entity_code)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(records), "failed": 0}
