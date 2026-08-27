"""Complaint and Return/Recall Feishu pages service.

Operates directly on Feishu Bitable tables for complaint and return/recall management.
Follows the same pattern as quality_feishu_pages_oos_oot.py.
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
    _create_entity_record,
    _delete_entity_record,
    _resolve_runtime_entity,
    _search_entity_records,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)


# ============ Helpers ============


def _map_nested_user(value: Any) -> str | None:
    """Extract user name/id from a Feishu user field value."""
    return feishu_sync_service._normalize_text(value)


def _map_checkbox(value: Any) -> bool:
    """Map Feishu checkbox field to bool."""
    return value is True or str(value).strip().lower() in ("true", "是", "已确认", "1")


# ============ Complaint Ledger ============

ENTITY_COMPLAINT_LEDGER = "complaint_ledger"
COMPLAINT_LEDGER_TEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("serial_number", "序号"),
    ("complaint_number", "投诉编号"),
    ("complaint_content", "投诉内容"),
    ("cause_analysis", "原因分析"),
    ("closing_deadline", "关闭时限"),
    ("complaint_level", "投诉级别"),
    ("complaint_unit", "投诉单位（个人）"),
    ("product_name", "品名"),
    ("quantity", "数量"),
    ("handling_result", "处理结果"),
    ("capa_result", "CAPA实施情况及结果"),
    ("batch_number", "批号"),
)


def _map_complaint_ledger(
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

    return {
        "record_id": str(record.get("record_id") or ""),
        "serial_number": normalize_text(field_value(entity, fields, "序号")),
        "complaint_number": normalize_text(field_value(entity, fields, "投诉编号")),
        "complaint_content": normalize_text(field_value(entity, fields, "投诉内容")),
        "cause_analysis": normalize_text(field_value(entity, fields, "原因分析")),
        "reply_date": parse_datetime(field_value(entity, fields, "回复日期")),
        "closing_deadline": normalize_text(field_value(entity, fields, "关闭时限")),
        "complaint_level": normalize_text(field_value(entity, fields, "投诉级别")),
        "complaint_unit": normalize_text(
            field_value(entity, fields, "投诉单位（个人）")
        ),
        "product_name": normalize_text(field_value(entity, fields, "品名")),
        "quantity": normalize_text(field_value(entity, fields, "数量")),
        "handling_result": normalize_text(field_value(entity, fields, "处理结果")),
        "capa_result": normalize_text(
            field_value(entity, fields, "CAPA实施情况及结果")
        ),
        "batch_number": normalize_text(field_value(entity, fields, "批号")),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_complaint_ledger_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_COMPLAINT_LEDGER, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_COMPLAINT_LEDGER)
    items = [_map_complaint_ledger(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in str(item.get(field_name) or "").lower()
                for field_name in (
                    "serial_number",
                    "complaint_number",
                    "complaint_content",
                    "cause_analysis",
                    "closing_deadline",
                    "complaint_level",
                    "complaint_unit",
                    "product_name",
                    "quantity",
                    "handling_result",
                    "capa_result",
                    "batch_number",
                )
            )
        ]

    items.sort(
        key=lambda x: str(x.get("reply_date") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_complaint_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_COMPLAINT_LEDGER, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_COMPLAINT_LEDGER)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_complaint_ledger(record, entity)
    raise NotFoundException(resource="投诉台账记录")


def _build_complaint_ledger_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Build Feishu bitable fields dict from payload."""
    fields: dict[str, Any] = {}

    for payload_key, feishu_key in COMPLAINT_LEDGER_TEXT_FIELDS:
        value = str(payload.get(payload_key) or "").strip()
        if value:
            fields[feishu_key] = value

    reply_date = payload.get("reply_date")
    if reply_date not in (None, ""):
        fields["回复日期"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(reply_date)
        )

    return fields


async def create_complaint_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    complaint_content = str(payload.get("complaint_content") or "").strip()
    if not complaint_content:
        raise AppException(message="投诉内容不能为空")
    fields = _build_complaint_ledger_fields(payload)
    created = await _create_entity_record(db, ENTITY_COMPLAINT_LEDGER, fields)
    return await get_complaint_ledger_record(db, created["record_id"])


async def update_complaint_ledger_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_complaint_ledger_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_complaint_ledger_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_COMPLAINT_LEDGER, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.update_record(entity.table_id, record_id, fields)
    return await get_complaint_ledger_record(db, record_id)


async def delete_complaint_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_COMPLAINT_LEDGER, record_id)


async def pull_complaint_ledger_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_COMPLAINT_LEDGER, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_complaint_ledger_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ Return Application (退货申请表) ============

ENTITY_RETURN_APPLICATION = "return_application"


def _map_return_application(
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

    return {
        "record_id": str(record.get("record_id") or ""),
        "serial_number": normalize_text(field_value(entity, fields, "序号")),
        "product_name": normalize_text(field_value(entity, fields, "品名")),
        "return_total": normalize_text(field_value(entity, fields, "退货总量")),
        "specification": normalize_text(field_value(entity, fields, "规格")),
        "batch_number": normalize_text(field_value(entity, fields, "批号")),
        "quantity": normalize_text(field_value(entity, fields, "数量")),
        "production_date": normalize_text(field_value(entity, fields, "生产日期")),
        "expiry_date": normalize_text(field_value(entity, fields, "有效期/复验期")),
        "batch_number1": normalize_text(field_value(entity, fields, "批号1")),
        "quantity1": normalize_text(field_value(entity, fields, "数量1")),
        "production_date1": normalize_text(field_value(entity, fields, "生产日期1")),
        "expiry_date1": normalize_text(field_value(entity, fields, "有效期/复验期1")),
        "batch_number2": normalize_text(field_value(entity, fields, "批号2")),
        "quantity2": normalize_text(field_value(entity, fields, "数量2")),
        "production_date2": normalize_text(field_value(entity, fields, "生产日期2")),
        "expiry_date2": normalize_text(field_value(entity, fields, "有效期/复验期2")),
        "remark": normalize_text(field_value(entity, fields, "备注")),
        "return_unit_address": normalize_text(
            field_value(entity, fields, "退货单位及地址")
        ),
        "return_reason": normalize_text(field_value(entity, fields, "退货原因")),
        "applicant": _map_nested_user(field_value(entity, fields, "申请人")),
        "application_date": parse_datetime(field_value(entity, fields, "申请日期")),
        "qa_head_opinion": normalize_text(field_value(entity, fields, "QA负责人意见")),
        "qa_head": _map_nested_user(field_value(entity, fields, "QA负责人")),
        "qa_head_date": parse_datetime(field_value(entity, fields, "QA负责人日期")),
        "quality_manager_suggestion": normalize_text(
            field_value(entity, fields, "质量管理负责人建议")
        ),
        "quality_manager": _map_nested_user(
            field_value(entity, fields, "质量管理负责人")
        ),
        "quality_manager_date": parse_datetime(
            field_value(entity, fields, "质量管理负责人日期")
        ),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_return_application_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_APPLICATION, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_RETURN_APPLICATION)
    items = [_map_return_application(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f)) or "").lower()
                for f in (
                    "product_name",
                    "batch_number",
                    "return_unit_address",
                    "return_reason",
                    "applicant",
                )
            )
        ]

    items.sort(
        key=lambda x: str(x.get("application_date") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_return_application_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_APPLICATION, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_RETURN_APPLICATION)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_return_application(record, entity)
    raise NotFoundException(resource="退货申请表记录")


def _build_return_application_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Build Feishu bitable fields dict from return application payload."""
    fields: dict[str, Any] = {}

    # Simple text fields
    for feishu_key, payload_key in (
        ("序号", "serial_number"),
        ("品名", "product_name"),
        ("退货总量", "return_total"),
        ("规格", "specification"),
        ("批号", "batch_number"),
        ("数量", "quantity"),
        ("生产日期", "production_date"),
        ("有效期/复验期", "expiry_date"),
        ("批号1", "batch_number1"),
        ("数量1", "quantity1"),
        ("生产日期1", "production_date1"),
        ("有效期/复验期1", "expiry_date1"),
        ("批号2", "batch_number2"),
        ("数量2", "quantity2"),
        ("生产日期2", "production_date2"),
        ("有效期/复验期2", "expiry_date2"),
        ("备注", "remark"),
        ("退货单位及地址", "return_unit_address"),
        ("退货原因", "return_reason"),
        ("QA负责人意见", "qa_head_opinion"),
        ("质量管理负责人建议", "quality_manager_suggestion"),
    ):
        val = (payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    # Date fields
    for feishu_key, payload_key in (
        ("申请日期", "application_date"),
        ("QA负责人日期", "qa_head_date"),
        ("质量管理负责人日期", "quality_manager_date"),
    ):
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = feishu_sync_service._to_ms_timestamp(
                feishu_sync_service._parse_feishu_datetime(val)
            )

    # User fields
    for feishu_key, payload_key in (
        ("申请人", "applicant"),
        ("QA负责人", "qa_head"),
        ("质量管理负责人", "quality_manager"),
    ):
        val = payload.get(payload_key)
        if val:
            if isinstance(val, dict) and val.get("id"):
                fields[feishu_key] = [val]
            elif isinstance(val, str) and val.strip():
                if val.strip().startswith("ou_"):
                    fields[feishu_key] = [{"id": val.strip()}]

    return fields


async def create_return_application_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    product_name = str(payload.get("product_name") or "").strip()
    if not product_name:
        raise AppException(message="品名不能为空")
    fields = _build_return_application_fields(payload)
    created = await _create_entity_record(db, ENTITY_RETURN_APPLICATION, fields)
    return await get_return_application_record(db, created["record_id"])


async def update_return_application_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_return_application_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_return_application_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_APPLICATION, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.update_record(entity.table_id, record_id, fields)
    return await get_return_application_record(db, record_id)


async def delete_return_application_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_RETURN_APPLICATION, record_id)


async def pull_return_application_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_RETURN_APPLICATION, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_return_application_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ Return Ledger (退回台账) ============

ENTITY_RETURN_LEDGER = "return_ledger"


def _map_return_ledger(
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
    quantity_value = field_value(entity, fields, "数量")

    return {
        "record_id": str(record.get("record_id") or ""),
        "serial_number": normalize_text(field_value(entity, fields, "序号")),
        "product_name": normalize_text(field_value(entity, fields, "品名")),
        "specification": normalize_text(field_value(entity, fields, "规格")),
        "product_batch_number": normalize_text(field_value(entity, fields, "产品批号")),
        "quantity": normalize_text(quantity_value),
        "return_unit_address": normalize_text(
            field_value(entity, fields, "退货单位及地址")
        ),
        "return_date": parse_datetime(field_value(entity, fields, "退回日期")),
        "operator": _map_nested_user(field_value(entity, fields, "经办人")),
        "disposal_result": normalize_text(
            field_value(entity, fields, "退回产品处理结果")
        ),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_return_ledger_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_LEDGER, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_RETURN_LEDGER)
    items = [_map_return_ledger(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(field_name) or "")).lower()
                for field_name in (
                    "product_name",
                    "product_batch_number",
                    "return_unit_address",
                    "operator",
                    "disposal_result",
                )
            )
        ]

    items.sort(
        key=lambda item: str(item.get("return_date") or item.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_return_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_LEDGER, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_RETURN_LEDGER)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_return_ledger(record, entity)
    raise NotFoundException(resource="退回台账记录")


def _build_return_ledger_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    for feishu_key, payload_key in (
        ("序号", "serial_number"),
        ("品名", "product_name"),
        ("规格", "specification"),
        ("产品批号", "product_batch_number"),
        ("退货单位及地址", "return_unit_address"),
        ("退回产品处理结果", "disposal_result"),
    ):
        value = str(payload.get(payload_key) or "").strip()
        if value:
            fields[feishu_key] = value

    quantity = payload.get("quantity")
    if quantity not in (None, ""):
        try:
            fields["数量"] = float(str(quantity))
        except (TypeError, ValueError) as exc:
            raise AppException(message="数量必须为数字") from exc

    return_date = payload.get("return_date")
    if return_date not in (None, ""):
        fields["退回日期"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(return_date)
        )

    operator = payload.get("operator")
    if isinstance(operator, dict) and operator.get("id"):
        fields["经办人"] = [operator]
    elif isinstance(operator, str) and operator.strip().startswith("ou_"):
        fields["经办人"] = [{"id": operator.strip()}]

    return fields


async def create_return_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    product_name = str(payload.get("product_name") or "").strip()
    if not product_name:
        raise AppException(message="品名不能为空")
    fields = _build_return_ledger_fields(payload)
    created = await _create_entity_record(db, ENTITY_RETURN_LEDGER, fields)
    return await get_return_ledger_record(db, created["record_id"])


async def update_return_ledger_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_return_ledger_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_return_ledger_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_RETURN_LEDGER, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.update_record(entity.table_id, record_id, fields)
    return await get_return_ledger_record(db, record_id)


async def delete_return_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_RETURN_LEDGER, record_id)


async def pull_return_ledger_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_RETURN_LEDGER, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_return_ledger_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}
