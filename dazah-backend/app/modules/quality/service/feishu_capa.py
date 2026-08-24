"""Feishu native CAPA service - direct bitable CRUD for CAPA ledger and plan track."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
    QualityFeishuRuntimeConfig,
    _require_table_id,
    _resolve_contact_bitable_user_value,
    feishu_sync,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Field-name constants (centralized Chinese field names)
# ──────────────────────────────────────────────


class CapaLedgerFields:
    """CAPA 台账飞书表中文字段名常量。"""

    START_DATE = "启动日期"
    CLOSE_DATE = "关闭日期"
    QA_CONFIRM_DATE = "QA质量员确认日期"
    QA_USER = "QA质量员"
    RELATED_CAPA_PLAN = "关联CAPA计划"
    DEPARTMENT = "事件部门"
    PRODUCT = "涉及产品"
    STATUS = "CAPA状态"


class CapaPlanTrackFields:
    """CAPA 计划跟踪飞书表中文字段名常量。"""

    COMPLETE_TIME = "完成时间"
    OWNER = "责任人"
    DEPT_OWNER = "部门负责人"
    RELATED_CAPA_CODE = "关联CAPA编号"
    OWNER_CONFIRMED = "责任人确认"
    DEPT_OWNER_CONFIRMED = "部门负责人确认"


# ──────────────────────────────────────────────
#  Field‑type descriptors (used for coercion)
# ──────────────────────────────────────────────
_CAPA_LEDGER_DATETIME_FIELDS = {
    CapaLedgerFields.START_DATE,
    CapaLedgerFields.CLOSE_DATE,
    CapaLedgerFields.QA_CONFIRM_DATE,
}
_CAPA_LEDGER_USER_FIELDS = {
    CapaLedgerFields.QA_USER,
}
_CAPA_LEDGER_READONLY_FIELDS = {
    CapaLedgerFields.RELATED_CAPA_PLAN,
}

_CAPA_PLAN_DATETIME_FIELDS = {
    CapaPlanTrackFields.COMPLETE_TIME,
}
_CAPA_PLAN_USER_FIELDS = {
    CapaPlanTrackFields.OWNER,
}
_CAPA_PLAN_READONLY_FIELDS = {
    CapaPlanTrackFields.DEPT_OWNER,
    CapaPlanTrackFields.RELATED_CAPA_CODE,
}
_CAPA_PLAN_CHECKBOX_FIELDS = {
    CapaPlanTrackFields.OWNER_CONFIRMED,
    CapaPlanTrackFields.DEPT_OWNER_CONFIRMED,
}

# ──────────────────────────────────────────────
#  Parse helpers  (Feishu raw -> Python dict)
# ──────────────────────────────────────────────


def _parse_date_field(value: Any) -> str | None:
    """Millisecond timestamp (int) -> YYYY‑MM‑DD string."""
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).strftime("%Y-%m-%d")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return datetime.fromtimestamp(int(stripped) / 1000, tz=UTC).strftime(
                "%Y-%m-%d"
            )
    return str(value)


def _parse_user_field(value: Any) -> str | None:
    """Feishu User list -> display name."""
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
    """Checkbox field -> bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "是", "已确认"}
    return bool(value)


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
    parser: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """将飞书原始记录列表转换为前端可用的 item 列表。

    Args:
        records: 飞书 bitable 返回的原始记录列表，每条包含 ``fields``、
            ``record_id``、``created_time``、``last_modified_time`` 等字段。
        parser: 字段解析回调，用于将单条记录的 ``fields`` 转换为干净的字段字典。

    Returns:
        转换后的 item 列表，每个 item 在 parser 输出的基础上追加 ``record_id``、
        ``created_time``、``last_modified_time`` 三个元数据字段。
    """
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
) -> tuple[QualityFeishuRuntimeConfig, QualityFeishuEntityRuntimeConfig]:
    runtime = await feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(entity_code, direction=direction)
    if (
        not runtime.is_enabled()
        or not entity
        or not entity.app_token
        or not entity.table_id
    ):
        raise AppException(status_code=400, message=f"{entity_code} 飞书 Base 未启用")
    return runtime, entity


def _make_client(
    runtime: QualityFeishuRuntimeConfig,
    entity: QualityFeishuEntityRuntimeConfig,
) -> BitableClient:
    return BitableClient(
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
    department = str(data.get(CapaLedgerFields.DEPARTMENT) or "").strip() or None
    for key, value in data.items():
        if key in readonly_fields:
            continue
        if key in datetime_fields:
            if value in (None, ""):
                continue
            if isinstance(value, str):
                fields[key] = int(
                    datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
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
            raise AppException(
                status_code=400,
                message=f"{key}“{normalized_value}”未在部门联系人中维护，无法写入飞书人员字段",
            )
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
    """获取飞书CAPA台账记录列表，支持关键词、部门、产品、状态过滤与分页。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        keyword: 关键词，在所有字段值中做大小写不敏感包含匹配；``None`` 表示不过滤。
        department: 事件部门精确匹配；``None`` 表示不过滤。
        product: 涉及产品包含匹配；``None`` 表示不过滤。
        status: CAPA状态精确匹配；``None`` 表示不过滤。
        page: 页码，从 1 开始。
        page_size: 每页条数。

    Returns:
        分页结果字典，包含 ``items``、``total``、``page``、``page_size`` 四个键。
    """
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(
        _require_table_id(entity), automatic_fields=True, page_size=500
    )
    items = _records_to_items(records, _parse_capa_ledger_fields)

    if keyword:
        items = [item for item in items if _contains_keyword(item, keyword)]
    if department:
        items = [
            item
            for item in items
            if (item.get(CapaLedgerFields.DEPARTMENT) or "") == department
        ]
    if product:
        items = [
            item
            for item in items
            if product in (item.get(CapaLedgerFields.PRODUCT) or "")
        ]
    if status:
        items = [
            item
            for item in items
            if (item.get(CapaLedgerFields.STATUS) or "") == status
        ]

    items.sort(
        key=lambda item: (
            item.get("last_modified_time") or item.get("created_time") or ""
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def get_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    """根据记录 ID 获取单条飞书CAPA台账详情。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        record_id: 飞书 bitable 记录 ID。

    Returns:
        解析后的台账字段字典，包含 ``record_id``、``created_time``、
        ``last_modified_time`` 等元数据。

    Raises:
        NotFoundException: 记录不存在时抛出。
    """
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="pull")
    client = _make_client(runtime, entity)
    record = await client.get_record(_require_table_id(entity), record_id)
    if not record:
        raise NotFoundException("飞书CAPA台账记录", record_id)
    item = _parse_capa_ledger_fields(record.get("fields") or {})
    item["record_id"] = record_id
    item["created_time"] = record.get("created_time")
    item["last_modified_time"] = record.get("last_modified_time")
    return item


async def create_capa_ledger_record(
    db: AsyncSession,
    data: dict[str, Any],
) -> dict[str, Any]:
    """在飞书CAPA台账表中创建一条新记录。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置及人员字段。
        data: 待写入的字段字典，键为中文字段名。

    Returns:
        创建成功后重新读取并解析的台账记录字典。

    Raises:
        AppException: 人员字段值未在部门联系人中维护时抛出 400 错误。
    """
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
    record = await client.create_record(_require_table_id(entity), fields)
    record_id = str(record.get("record_id") or "")
    logger.info("CAPA ledger record created", extra={"record_id": record_id})
    return await get_capa_ledger_record(db, record_id)


async def update_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """根据记录 ID 更新飞书CAPA台账字段。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置及人员字段。
        record_id: 飞书 bitable 记录 ID。
        data: 待更新的字段字典，键为中文字段名。

    Returns:
        更新成功后重新读取并解析的台账记录字典。

    Raises:
        AppException: 人员字段值未在部门联系人中维护时抛出 400 错误。
    """
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
    await client.update_record(_require_table_id(entity), record_id, fields)
    logger.info("CAPA ledger record updated", extra={"record_id": record_id})
    return await get_capa_ledger_record(db, record_id)


async def delete_capa_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    """根据记录 ID 删除飞书CAPA台账记录。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        record_id: 飞书 bitable 记录 ID。
    """
    runtime, entity = await _resolve_entity(db, "capa_ledger", direction="push")
    client = _make_client(runtime, entity)
    await client.delete_record(_require_table_id(entity), record_id)
    logger.info("CAPA ledger record deleted", extra={"record_id": record_id})


# ══════════════════════════════════════════════
#  CAPA 计划跟踪 CRUD
# ══════════════════════════════════════════════


async def list_capa_plan_tracks(
    db: AsyncSession,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """获取飞书CAPA计划跟踪记录列表，支持关键词过滤与分页。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        keyword: 关键词，在所有字段值中做大小写不敏感包含匹配；``None`` 表示不过滤。
        page: 页码，从 1 开始。
        page_size: 每页条数。

    Returns:
        分页结果字典，包含 ``items``、``total``、``page``、``page_size`` 四个键。
    """
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="pull")
    client = _make_client(runtime, entity)
    records = await client.search_records(
        _require_table_id(entity), automatic_fields=True, page_size=500
    )
    items = _records_to_items(records, _parse_capa_plan_track_fields)

    if keyword:
        items = [item for item in items if _contains_keyword(item, keyword)]

    items.sort(
        key=lambda item: (
            item.get("last_modified_time") or item.get("created_time") or ""
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def get_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    """根据记录 ID 获取单条飞书CAPA计划跟踪详情。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        record_id: 飞书 bitable 记录 ID。

    Returns:
        解析后的计划跟踪字段字典，包含 ``record_id``、``created_time``、
        ``last_modified_time`` 等元数据。

    Raises:
        NotFoundException: 记录不存在时抛出。
    """
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="pull")
    client = _make_client(runtime, entity)
    record = await client.get_record(_require_table_id(entity), record_id)
    if not record:
        raise NotFoundException("飞书CAPA计划跟踪记录", record_id)
    item = _parse_capa_plan_track_fields(record.get("fields") or {})
    item["record_id"] = record_id
    item["created_time"] = record.get("created_time")
    item["last_modified_time"] = record.get("last_modified_time")
    return item


async def create_capa_plan_track_record(
    db: AsyncSession,
    data: dict[str, Any],
) -> dict[str, Any]:
    """在飞书CAPA计划跟踪表中创建一条新记录。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置及人员字段。
        data: 待写入的字段字典，键为中文字段名。

    Returns:
        创建成功后重新读取并解析的计划跟踪记录字典。

    Raises:
        AppException: 人员字段值未在部门联系人中维护时抛出 400 错误。
    """
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
    record = await client.create_record(_require_table_id(entity), fields)
    record_id = str(record.get("record_id") or "")
    logger.info("CAPA plan track record created", extra={"record_id": record_id})
    return await get_capa_plan_track_record(db, record_id)


async def update_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """根据记录 ID 更新飞书CAPA计划跟踪字段。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置及人员字段。
        record_id: 飞书 bitable 记录 ID。
        data: 待更新的字段字典，键为中文字段名。

    Returns:
        更新成功后重新读取并解析的计划跟踪记录字典。

    Raises:
        AppException: 人员字段值未在部门联系人中维护时抛出 400 错误。
    """
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
    await client.update_record(_require_table_id(entity), record_id, fields)
    logger.info("CAPA plan track record updated", extra={"record_id": record_id})
    return await get_capa_plan_track_record(db, record_id)


async def delete_capa_plan_track_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    """根据记录 ID 删除飞书CAPA计划跟踪记录。

    Args:
        db: 异步数据库会话，用于解析飞书运行时配置。
        record_id: 飞书 bitable 记录 ID。
    """
    runtime, entity = await _resolve_entity(db, "capa_plan_track", direction="push")
    client = _make_client(runtime, entity)
    await client.delete_record(_require_table_id(entity), record_id)
    logger.info("CAPA plan track record deleted", extra={"record_id": record_id})
