"""Feishu native CAPA service — direct bitable CRUD for CAPA ledger and plan track."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.quality_feishu_sync import (
    _resolve_contact_bitable_user_value,
    feishu_sync,
)
from app.platform.integrations.feishu.utils import build_bitable_client

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Field‑type descriptors (used for coercion)
# ──────────────────────────────────────────────
_CAPA_LEDGER_DATETIME_FIELDS = {
    "启动日期",
    "关闭日期",
    "QA质量员确认日期",
}
_CAPA_LEDGER_USER_FIELDS = {
    "QA质量员",
}
_CAPA_LEDGER_READONLY_FIELDS = {
    "关联CAPA计划",
}

_CAPA_PLAN_DATETIME_FIELDS = {
    "完成时间",
}
_CAPA_PLAN_USER_FIELDS = {
    "责任人",
}
_CAPA_PLAN_READONLY_FIELDS = {
    "部门负责人",
    "关联CAPA编号",
}
_CAPA_PLAN_CHECKBOX_FIELDS = {
    "责任人确认",
    "部门负责人确认",
}

# ──────────────────────────────────────────────
#  Parse helpers  (Feishu raw → Python dict)
# ──────────────────────────────────────────────


def _parse_date_field(value: Any) -> str | None:
    """Millisecond timestamp (int) → YYYY‑MM‑DD string."""
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return datetime.fromtimestamp(int(stripped) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(value)


def _parse_user_field(value: Any) -> str | None:
    """Feishu User list → display name."""
    if not value:
        return None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    return str(name)
        if value:
            first = value[0]
            if isinstance(first, dict):
                return str(first.get("id") or "")
            return str(first)
        return None
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "")
    return str(value)


def _parse_checkbox_field(value: Any) -> bool:
    """Checkbox field → bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "是", "已确认"}
    return bool(value)


def _parse_single_select(value: Any) -> str:
    """SingleSelect field → string."""
    if value in (None, "", []):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "")
    return str(value)


def _parse_text_field(value: Any) -> str | None:
    """Extract plain text from Feishu text/rich-text field (may be array of objects)."""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts) if parts else None
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(value)


# ──────────────────────────────────────────────
#  Record‑level parse helpers
# ──────────────────────────────────────────────


def _parse_capa_ledger_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw CAPA ledger Feishu fields dict into a clean Python dict."""
    result: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _CAPA_LEDGER_DATETIME_FIELDS:
            result[key] = _parse_date_field(value)
        elif key in _CAPA_LEDGER_USER_FIELDS:
            result[key] = _parse_user_field(value)
        elif key in _CAPA_LEDGER_READONLY_FIELDS:
            continue
        else:
            result[key] = _parse_text_field(value)
    return result


def _parse_capa_plan_track_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw CAPA plan track Feishu fields dict into a clean Python dict."""
    result: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _CAPA_PLAN_DATETIME_FIELDS:
            result[key] = _parse_date_field(value)
        elif key in _CAPA_PLAN_USER_FIELDS:
            result[key] = _parse_user_field(value)
        elif key in _CAPA_PLAN_CHECKBOX_FIELDS:
            result[key] = _parse_checkbox_field(value)
        elif key in _CAPA_PLAN_READONLY_FIELDS:
            continue
        else:
            result[key] = _parse_text_field(value)
    return result


def _records_to_items(
    records: list[dict[str, Any]],
    parser: Any,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        item = parser(fields)
        item["record_id"] = str(record.get("record_id") or "")
        item["created_time"] = record.get("created_time")
        item["last_modified_time"] = record.get("last_modified_time")
        items.append(item)
    return items


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────


async def _resolve_entity(
    db: AsyncSession,
    entity_code: str,
    direction: str,
) -> tuple[feishu_sync.QualityFeishuRuntimeConfig, feishu_sync.QualityFeishuEntityRuntimeConfig]:
    runtime = await feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(entity_code, direction=direction)
    if not runtime.is_enabled() or not entity or not entity.app_token or not entity.table_id:
        raise ValueError(f"{entity_code} 飞书 Base 未启用")
    return runtime, entity


def _make_client(
    runtime: feishu_sync.QualityFeishuRuntimeConfig,
    entity: feishu_sync.QualityFeishuEntityRuntimeConfig,
) -> Any:
    return build_bitable_client(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )


def _looks_like_bitable_user_id(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    return normalized.startswith(("ou_", "on_", "u_", "cli_"))


async def _coerce_write_fields(
    db: AsyncSession,
    data: dict[str, Any],
    *,
    datetime_fields: set[str],
    user_fields: set[str],
    checkbox_fields: set[str],
    readonly_fields: set[str],
) -> dict[str, Any]:
    """Prepare a fields dict for Feishu write (create / update)."""
    fields: dict[str, Any] = {}
    department = str(data.get("事件部门") or "").strip() or None
    for key, value in data.items():
        if key in readonly_fields:
            continue
        if key in datetime_fields:
            if value in (None, ""):
                continue
            if isinstance(value, str):
                fields[key] = int(
                    datetime.strptime(value, "%Y-%m-%d")
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                    * 1000
                )
            elif isinstance(value, (int, float)):
                fields[key] = int(value)
            continue
        if key in user_fields:
            if value in (None, ""):
                continue
            if isinstance(value, list):
                fields[key] = value
                continue
            if isinstance(value, dict):
                fields[key] = [value]
                continue
            normalized_value = str(value).strip()
            if not normalized_value:
                continue
            resolved_user_value = await _resolve_contact_bitable_user_value(
                db,
                normalized_value,
                department=department,
            )
            if resolved_user_value:
                fields[key] = resolved_user_value
                continue
            if _looks_like_bitable_user_id(normalized_value):
                fields[key] = [{"id": normalized_value}]
                continue
            raise ValueError(
                f"{key}“{normalized_value}”未在部门联系人中维护，无法写入飞书人员字段"
            )
            continue
        if key in checkbox_fields:
            fields[key] = bool(value)
            continue
        fields[key] = value
    return fields


def _contains_keyword(item: dict[str, Any], keyword: str | None) -> bool:
    if not keyword:
        return True
    kw = keyword.lower()
    for field_value in item.values():
        if field_value is None:
            continue
        if isinstance(field_value, str) and kw in field_value.lower():
            return True
    return False


def _build_page_result(
    items: list[dict[str, Any]],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ══════════════════════════════════════════════
#  CAPA 台账 CRUD
# ══════════════════════════════════════════════


async def list_capa_ledger(
    db: AsyncSession,
    keyword: str | None = None,
    department: str | None = None,
    product: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(entity.table_id, automatic_fields=True, page_size=500)
    items = _records_to_items(records, _parse_capa_ledger_fields)

    if keyword:
        items = [item for item in items if _contains_keyword(item, keyword)]
    if department:
        items = [item for item in items if (item.get("事件部门") or "") == department]
    if product:
        items = [item for item in items if product in (item.get("涉及产品") or "")]
    if status:
        items = [item for item in items if (item.get("CAPA状态") or "") == status]

    items.sort(
        key=lambda item: item.get("last_modified_time") or item.get("created_time") or "",
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def get_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(entity.table_id, automatic_fields=True, page_size=500)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            item = _parse_capa_ledger_fields(record.get("fields") or {})
            item["record_id"] = record_id
            item["created_time"] = record.get("created_time")
            item["last_modified_time"] = record.get("last_modified_time")
            return item
    raise ValueError("飞书CAPA台账记录不存在")


async def create_capa_ledger_record(
    db: AsyncSession,
    data: dict[str, Any],
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="push")
    client = _make_client(runtime, entity)
    fields = await _coerce_write_fields(
        db,
        data,
        datetime_fields=_CAPA_LEDGER_DATETIME_FIELDS,
        user_fields=_CAPA_LEDGER_USER_FIELDS,
        checkbox_fields=set(),
        readonly_fields=_CAPA_LEDGER_READONLY_FIELDS,
    )
    record = await client.create_record(entity.table_id, fields)
    record_id = str(record.get("record_id") or "")
    return await get_capa_ledger_record(db, record_id)


async def update_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="push")
    client = _make_client(runtime, entity)
    fields = await _coerce_write_fields(
        db,
        data,
        datetime_fields=_CAPA_LEDGER_DATETIME_FIELDS,
        user_fields=_CAPA_LEDGER_USER_FIELDS,
        checkbox_fields=set(),
        readonly_fields=_CAPA_LEDGER_READONLY_FIELDS,
    )
    await client.update_record(entity.table_id, record_id, fields)
    return await get_capa_ledger_record(db, record_id)


async def delete_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="push")
    client = _make_client(runtime, entity)
    await client.delete_record(entity.table_id, record_id)


# ══════════════════════════════════════════════
#  CAPA 计划跟踪 CRUD
# ══════════════════════════════════════════════


async def list_capa_plan_tracks(
    db: AsyncSession,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(entity.table_id, automatic_fields=True, page_size=500)
    items = _records_to_items(records, _parse_capa_plan_track_fields)

    if keyword:
        items = [item for item in items if _contains_keyword(item, keyword)]

    items.sort(
        key=lambda item: item.get("last_modified_time") or item.get("created_time") or "",
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def get_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(entity.table_id, automatic_fields=True, page_size=500)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            item = _parse_capa_plan_track_fields(record.get("fields") or {})
            item["record_id"] = record_id
            item["created_time"] = record.get("created_time")
            item["last_modified_time"] = record.get("last_modified_time")
            return item
    raise ValueError("飞书CAPA计划跟踪记录不存在")


async def create_capa_plan_track_record(
    db: AsyncSession,
    data: dict[str, Any],
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="push")
    client = _make_client(runtime, entity)
    fields = await _coerce_write_fields(
        db,
        data,
        datetime_fields=_CAPA_PLAN_DATETIME_FIELDS,
        user_fields=_CAPA_PLAN_USER_FIELDS,
        checkbox_fields=_CAPA_PLAN_CHECKBOX_FIELDS,
        readonly_fields=_CAPA_PLAN_READONLY_FIELDS,
    )
    record = await client.create_record(entity.table_id, fields)
    record_id = str(record.get("record_id") or "")
    return await get_capa_plan_track_record(db, record_id)


async def update_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="push")
    client = _make_client(runtime, entity)
    fields = await _coerce_write_fields(
        db,
        data,
        datetime_fields=_CAPA_PLAN_DATETIME_FIELDS,
        user_fields=_CAPA_PLAN_USER_FIELDS,
        checkbox_fields=_CAPA_PLAN_CHECKBOX_FIELDS,
        readonly_fields=_CAPA_PLAN_READONLY_FIELDS,
    )
    await client.update_record(entity.table_id, record_id, fields)
    return await get_capa_plan_track_record(db, record_id)


async def delete_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="push")
    client = _make_client(runtime, entity)
    await client.delete_record(entity.table_id, record_id)
