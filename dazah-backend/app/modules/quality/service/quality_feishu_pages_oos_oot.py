"""OOS/OOT Feishu pages service.

Operates directly on Feishu Bitable tables for OOS/OOT management.
Follows the same pattern as quality_feishu_pages.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import (
    quality_feishu_sync as feishu_sync_service,
)
from app.modules.quality.service.quality_feishu_pages import (
    _build_page_result,
    _create_entity_record,
    _delete_entity_record,
    _resolve_runtime_entity,
    _search_entity_records,
    _update_entity_record,
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


# ============ OOSOOT Report Record ============

ENTITY_OOS_OOT_REPORT_RECORD = "oos_oot_report_record"


def _map_oos_oot_report_record(
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
        "report_time": parse_datetime(field_value(entity, fields, "报告时间")),
        "content": normalize_text(field_value(entity, fields, "内容")),
        "product_name": normalize_text(field_value(entity, fields, "涉及产品名称")),
        "batch_number": normalize_text(field_value(entity, fields, "涉及批号")),
        "report_department": normalize_text(field_value(entity, fields, "报告部门")),
        "reporter": _map_nested_user(field_value(entity, fields, "报告人")),
        "reporters": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "报告人")
        ),
        "department_head": _map_nested_user(field_value(entity, fields, "部门负责人")),
        "department_heads": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "部门负责人")
        ),
        "department_head_confirmed": _map_checkbox(
            field_value(entity, fields, "部门负责人确认")
        ),
        "fermentation_head": _map_nested_user(
            field_value(entity, fields, "涉及发酵负责人")
        ),
        "fermentation_head_confirmed": _map_checkbox(
            field_value(entity, fields, "涉及发酵负责人确认")
        ),
        "extraction_head": _map_nested_user(
            field_value(entity, fields, "涉及提炼负责人")
        ),
        "extraction_head_confirmed": _map_checkbox(
            field_value(entity, fields, "涉及提炼负责人确认")
        ),
        "qa": _map_nested_user(field_value(entity, fields, "QA")),
        "qas": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "QA")
        ),
        "qa_confirmed": _map_checkbox(field_value(entity, fields, "QA确认")),
        "qa_head": _map_nested_user(field_value(entity, fields, "QA负责人")),
        "qa_heads": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "QA负责人")
        ),
        "qa_head_confirmed": _map_checkbox(field_value(entity, fields, "QA负责人确认")),
        "attachments": feishu_sync_service._parse_attachment_field(
            field_value(entity, fields, "附件")
        ),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_oos_oot_report_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_REPORT_RECORD, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_REPORT_RECORD)
    items = [_map_oos_oot_report_record(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f)) or "").lower()
                for f in (
                    "content",
                    "product_name",
                    "batch_number",
                    "report_department",
                    "reporter",
                )
            )
        ]

    items.sort(
        key=lambda x: str(x.get("report_time") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_oos_oot_report_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_REPORT_RECORD, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_REPORT_RECORD)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_oos_oot_report_record(record, entity)
    raise NotFoundException(resource="OOSOOT报告记录")


def _build_oos_oot_report_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Build Feishu bitable fields dict from payload."""
    fields: dict[str, Any] = {}
    for feishu_key, payload_key in (("报告时间", "report_time"),):
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = feishu_sync_service._to_ms_timestamp(
                feishu_sync_service._parse_feishu_datetime(val)
            )
    simple_fields = {
        "内容": "content",
        "涉及产品名称": "product_name",
        "涉及批号": "batch_number",
        "报告部门": "report_department",
    }
    for feishu_key, payload_key in simple_fields.items():
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = str(val).strip()

    # User fields - resolve by name from department contacts
    for feishu_key, payload_key in (
        ("报告人", "reporter"),
        ("QA", "qa"),
        ("QA负责人", "qa_head"),
    ):
        val = payload.get(payload_key)
        if val:
            # Support both name strings and open_id/bitable_user_id
            if isinstance(val, dict) and val.get("id"):
                fields[feishu_key] = [val]
            elif isinstance(val, str) and val.strip():
                fields[feishu_key] = [{"id": val.strip()}]

    # Boolean checkbox fields
    for feishu_key, payload_key in (
        ("部门负责人确认", "department_head_confirmed"),
        ("涉及发酵负责人确认", "fermentation_head_confirmed"),
        ("涉及提炼负责人确认", "extraction_head_confirmed"),
        ("QA确认", "qa_confirmed"),
        ("QA负责人确认", "qa_head_confirmed"),
    ):
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = bool(val)
    return fields


async def _resolve_user_from_contacts(
    db: AsyncSession,
    name_or_id: str | None,
    department: str | None = None,
) -> dict[str, str] | None:
    """Resolve user field value from department contacts or direct open_id."""
    if not name_or_id:
        return None
    # If it looks like an open_id, return as-is
    if name_or_id.startswith("ou_"):
        return {"id": name_or_id}
    # Try to find in department contacts
    try:
        contacts = await feishu_sync_service.feishu_sync._get_department_contacts(db)
        for contact in contacts:
            contact_name = str(contact.get("name") or "").strip()
            if contact_name == name_or_id.strip():
                user_id = str(
                    contact.get("bitable_user_id") or contact.get("open_id") or ""
                ).strip()
                if user_id:
                    return {"id": user_id}
    except Exception:
        logger.warning(
            "解析用户ID失败，回退使用原始值 name_or_id=%s", name_or_id, exc_info=True
        )
    return {"id": name_or_id.strip()}


def _build_oos_oot_report_feishu_fields_async(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build Feishu fields for OOSOOT report record (sync version for API use)."""
    fields: dict[str, Any] = {}

    # Date - only set if explicitly provided in payload
    report_time = payload.get("report_time")
    if report_time is not None:
        fields["报告时间"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(report_time)
        )

    # Simple text fields
    for feishu_key, payload_key in (
        ("内容", "content"),
        ("涉及产品名称", "product_name"),
        ("涉及批号", "batch_number"),
        ("报告部门", "report_department"),
    ):
        val = (payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    # User fields - only send if value looks like a valid user ID
    for feishu_key, payload_key in (
        ("报告人", "reporter"),
        ("QA", "qa"),
        ("QA负责人", "qa_head"),
    ):
        val = payload.get(payload_key)
        if val:
            if isinstance(val, dict) and val.get("id"):
                fields[feishu_key] = [val]
            elif isinstance(val, str) and val.strip():
                # Only send if it looks like an open_id/bitable_user_id
                if val.strip().startswith("ou_"):
                    fields[feishu_key] = [{"id": val.strip()}]

    # Checkbox fields
    for feishu_key, payload_key in (
        ("部门负责人确认", "department_head_confirmed"),
        ("QA确认", "qa_confirmed"),
        ("QA负责人确认", "qa_head_confirmed"),
    ):
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = bool(val)
    return fields


async def create_oos_oot_report_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    content = str(payload.get("content") or "").strip()
    if not content:
        raise AppException(message="内容不能为空")
    fields = _build_oos_oot_report_feishu_fields_async(db, payload)
    created = await _create_entity_record(db, ENTITY_OOS_OOT_REPORT_RECORD, fields)
    return await get_oos_oot_report_record(db, created["record_id"])


async def update_oos_oot_report_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_oos_oot_report_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_oos_oot_report_feishu_fields_async(db, merged)
    # Exclude auto-generated fields from update
    fields.pop("报告时间", None)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_REPORT_RECORD, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.update_record(entity.table_id, record_id, fields)
    return await get_oos_oot_report_record(db, record_id)


async def delete_oos_oot_report_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_OOS_OOT_REPORT_RECORD, record_id)


async def pull_oos_oot_report_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_OOS_OOT_REPORT_RECORD, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_oos_oot_report_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ OOSOOT Investigation Push Record ============

ENTITY_OOS_OOT_INVESTIGATION_PUSH = "oos_oot_investigation_push"


def _map_oos_oot_investigation_push(
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

    # URL field
    report_url_raw = field_value(entity, fields, "调查报告")
    report_url = None
    if isinstance(report_url_raw, dict):
        report_url = report_url_raw.get("link") or report_url_raw.get("text")
    elif report_url_raw:
        report_url = str(report_url_raw).strip() or None

    return {
        "record_id": str(record.get("record_id") or ""),
        "oos_oot_code": normalize_text(field_value(entity, fields, "OOS/OOT编号")),
        "push_round": normalize_text(field_value(entity, fields, "第N次推送")),
        "investigation_report_url": report_url,
        "submitted_at": parse_datetime(field_value(entity, fields, "提交日期")),
        "department": normalize_text(field_value(entity, fields, "部门")),
        "submitter": _map_nested_user(field_value(entity, fields, "提交人")),
        "submitters": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "提交人")
        ),
        "department_head": _map_nested_user(field_value(entity, fields, "部门负责人")),
        "department_heads": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "部门负责人")
        ),
        "department_head_result": normalize_text(
            field_value(entity, fields, "部门负责人审核结果")
        ),
        "department_head_reviewed_at": parse_datetime(
            field_value(entity, fields, "部门负责人审核时间")
        ),
        "qa": _map_nested_user(field_value(entity, fields, "QA")),
        "qas": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "QA")
        ),
        "qa_result": normalize_text(field_value(entity, fields, "QA审核结果")),
        "qa_reviewed_at": parse_datetime(field_value(entity, fields, "QA审核时间")),
        "qa_head": _map_nested_user(field_value(entity, fields, "QA负责人")),
        "qa_heads": feishu_sync_service._parse_person_field(
            field_value(entity, fields, "QA负责人")
        ),
        "qa_head_result": normalize_text(
            field_value(entity, fields, "QA负责人审核结果")
        ),
        "qa_head_reviewed_at": parse_datetime(
            field_value(entity, fields, "QA负责人审核时间")
        ),
        "process_status": normalize_text(field_value(entity, fields, "流程状态")),
        "need_resubmit": _map_checkbox(field_value(entity, fields, "已退回待重新提交")),
        "department_head_direct": _map_nested_user(
            field_value(entity, fields, "部门负责人(直接)")
        ),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_oos_oot_investigation_push_records(
    db: AsyncSession,
    *,
    oos_oot_code: str | None = None,
    push_round: str | None = None,
    department_head_result: str | None = None,
    qa_result: str | None = None,
    qa_head_result: str | None = None,
    process_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_INVESTIGATION_PUSH)
    items = [_map_oos_oot_investigation_push(record, entity) for record in records]

    # Filters
    if oos_oot_code:
        items = [
            item for item in items if (item.get("oos_oot_code") or "") == oos_oot_code
        ]
    if push_round:
        items = [item for item in items if (item.get("push_round") or "") == push_round]
    if department_head_result:
        items = [
            item
            for item in items
            if (item.get("department_head_result") or "") == department_head_result
        ]
    if qa_result:
        items = [item for item in items if (item.get("qa_result") or "") == qa_result]
    if qa_head_result:
        items = [
            item
            for item in items
            if (item.get("qa_head_result") or "") == qa_head_result
        ]
    if process_status:
        items = [
            item
            for item in items
            if (item.get("process_status") or "") == process_status
        ]

    items.sort(
        key=lambda x: str(x.get("submitted_at") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_oos_oot_investigation_push_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_INVESTIGATION_PUSH)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_oos_oot_investigation_push(record, entity)
    raise NotFoundException(resource="OOSOOT调查推送记录")


def _build_oos_oot_investigation_push_feishu_fields(
    payload: dict[str, Any],
) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    for feishu_key, payload_key in (
        ("OOS/OOT编号", "oos_oot_code"),
        ("第N次推送", "push_round"),
        ("部门", "department"),
        ("部门负责人审核结果", "department_head_result"),
        ("QA审核结果", "qa_result"),
        ("QA负责人审核结果", "qa_head_result"),
        ("流程状态", "process_status"),
    ):
        val = (payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    # URL
    url = (payload.get("investigation_report_url") or "").strip()
    if url:
        fields["调查报告"] = {"link": url, "text": url, "type": "url"}

    # Date times
    for feishu_key, payload_key in (
        ("提交日期", "submitted_at"),
        ("部门负责人审核时间", "department_head_reviewed_at"),
        ("QA审核时间", "qa_reviewed_at"),
        ("QA负责人审核时间", "qa_head_reviewed_at"),
    ):
        val = payload.get(payload_key)
        if val is not None:
            fields[feishu_key] = feishu_sync_service._to_ms_timestamp(
                feishu_sync_service._parse_feishu_datetime(val)
            )

    # User fields - only send if value looks like a valid user ID
    for feishu_key, payload_key in (
        ("提交人", "submitter"),
        ("QA", "qa"),
        ("QA负责人", "qa_head"),
        ("部门负责人(直接)", "department_head_direct"),
    ):
        val = payload.get(payload_key)
        if val:
            if isinstance(val, dict) and val.get("id"):
                fields[feishu_key] = [val]
            elif isinstance(val, str) and val.strip():
                if val.strip().startswith("ou_"):
                    fields[feishu_key] = [{"id": val.strip()}]

    # Checkbox
    if payload.get("need_resubmit") is not None:
        fields["已退回待重新提交"] = bool(payload["need_resubmit"])

    return fields


async def create_oos_oot_investigation_push_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    oos_oot_code = str(payload.get("oos_oot_code") or "").strip()
    if not oos_oot_code:
        raise AppException(message="OOS/OOT编号不能为空")
    fields = _build_oos_oot_investigation_push_feishu_fields(payload)
    created = await _create_entity_record(db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, fields)
    return await get_oos_oot_investigation_push_record(db, created["record_id"])


async def update_oos_oot_investigation_push_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_oos_oot_investigation_push_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_oos_oot_investigation_push_feishu_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.update_record(entity.table_id, record_id, fields)
    return await get_oos_oot_investigation_push_record(db, record_id)


async def delete_oos_oot_investigation_push_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, record_id)


async def pull_oos_oot_investigation_push_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_OOS_OOT_INVESTIGATION_PUSH, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_oos_oot_investigation_push_records(
            db, page=1, page_size=10000
        )
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ OOS Ledger ============

ENTITY_OOS_LEDGER = "oos_ledger"


def _map_oos_ledger(
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
        "date": parse_datetime(field_value(entity, fields, "日期")),
        "material_name": normalize_text(field_value(entity, fields, "物料名称")),
        "batch_number": normalize_text(field_value(entity, fields, "批号")),
        "investigation_code": normalize_text(field_value(entity, fields, "调查编号")),
        "problem_description": normalize_text(field_value(entity, fields, "问题描述")),
        "root_cause": normalize_text(field_value(entity, fields, "产生原因")),
        "corrective_actions": normalize_text(
            field_value(entity, fields, "纠正预防措施")
        ),
        "final_disposition": normalize_text(
            field_value(entity, fields, "最终处理结果")
        ),
        "registrant": normalize_text(field_value(entity, fields, "登记人")),
        "remark": normalize_text(field_value(entity, fields, "备注")),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_oos_ledger_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, ENTITY_OOS_LEDGER, direction="pull")
    records = await _search_entity_records(db, ENTITY_OOS_LEDGER)
    items = [_map_oos_ledger(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f)) or "").lower()
                for f in (
                    "material_name",
                    "batch_number",
                    "investigation_code",
                    "problem_description",
                    "registrant",
                )
            )
        ]

    items.sort(
        key=lambda x: str(x.get("date") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_oos_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, ENTITY_OOS_LEDGER, direction="pull")
    records = await _search_entity_records(db, ENTITY_OOS_LEDGER)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_oos_ledger(record, entity)
    raise NotFoundException(resource="OOS台账记录")


def _build_ledger_feishu_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    serial_val = (payload.get("serial_number") or "").strip()
    if serial_val:
        try:
            fields["序号"] = int(serial_val)
        except ValueError:
            fields["序号"] = serial_val
    for feishu_key, payload_key in (
        ("物料名称", "material_name"),
        ("批号", "batch_number"),
        ("调查编号", "investigation_code"),
        ("问题描述", "problem_description"),
        ("产生原因", "root_cause"),
        ("纠正预防措施", "corrective_actions"),
        ("最终处理结果", "final_disposition"),
        ("备注", "remark"),
    ):
        val = (payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val
    # 登记人：人员字段，传 open_id（前端 Select 直接传 open_id）
    registrant_val = (payload.get("registrant") or "").strip()
    if registrant_val and registrant_val.startswith("ou_"):
        fields["登记人"] = [{"id": registrant_val}]
    date_val = payload.get("date")
    if date_val is not None:
        fields["日期"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(date_val)
        )
    return fields


async def _auto_serial_number(db: AsyncSession, entity_code: str) -> int:
    """Auto-generate the next serial number based on existing records."""
    try:
        records = await _search_entity_records(db, entity_code)
        max_serial = 0
        field_value = feishu_sync_service._get_mapped_field_value
        for record in records:
            fields = record.get("fields") or {}
            raw = feishu_sync_service._normalize_text(
                field_value(
                    feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                        app_token="",
                        table_id="",
                        is_enabled=True,
                        enable_push_to_feishu=True,
                        enable_pull_from_feishu=True,
                        field_mappings={},
                    ),
                    fields,
                    "序号",
                )
            )
            if raw:
                try:
                    num = int(raw)
                    if num > max_serial:
                        max_serial = num
                except AppException as e:
                    logger.debug("跳过无效序号: %s", e)
        return max_serial + 1
    except Exception:
        return 1


async def create_oos_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    serial = str(payload.get("serial_number") or "").strip()
    if not serial:
        serial = str(await _auto_serial_number(db, ENTITY_OOS_LEDGER))
        payload["serial_number"] = serial
    fields = _build_ledger_feishu_fields(payload)
    created = await _create_entity_record(db, ENTITY_OOS_LEDGER, fields)
    return await get_oos_ledger_record(db, created["record_id"])


async def update_oos_ledger_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_oos_ledger_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_ledger_feishu_fields(merged)
    await _update_entity_record(db, ENTITY_OOS_LEDGER, record_id, fields)
    return await get_oos_ledger_record(db, record_id)


async def delete_oos_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_OOS_LEDGER, record_id)


async def pull_oos_ledger_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_OOS_LEDGER, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_oos_ledger_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ OOT Ledger ============

ENTITY_OOT_LEDGER = "oot_ledger"


def _map_oot_ledger(
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
        "date": parse_datetime(field_value(entity, fields, "日期")),
        "material_name": normalize_text(field_value(entity, fields, "物料名称")),
        "batch_number": normalize_text(field_value(entity, fields, "批号")),
        "investigation_code": normalize_text(field_value(entity, fields, "调查编号")),
        "problem_description": normalize_text(field_value(entity, fields, "问题描述")),
        "root_cause": normalize_text(field_value(entity, fields, "产生原因")),
        "corrective_actions": normalize_text(
            field_value(entity, fields, "纠正预防措施")
        ),
        "final_disposition": normalize_text(
            field_value(entity, fields, "最终处理结果")
        ),
        "registrant": normalize_text(field_value(entity, fields, "登记人")),
        "remark": normalize_text(field_value(entity, fields, "备注")),
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_oot_ledger_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, ENTITY_OOT_LEDGER, direction="pull")
    records = await _search_entity_records(db, ENTITY_OOT_LEDGER)
    items = [_map_oot_ledger(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f)) or "").lower()
                for f in (
                    "material_name",
                    "batch_number",
                    "investigation_code",
                    "problem_description",
                    "registrant",
                )
            )
        ]

    items.sort(
        key=lambda x: str(x.get("date") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_oot_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, ENTITY_OOT_LEDGER, direction="pull")
    records = await _search_entity_records(db, ENTITY_OOT_LEDGER)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_oot_ledger(record, entity)
    raise NotFoundException(resource="OOT台账记录")


async def create_oot_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    serial = str(payload.get("serial_number") or "").strip()
    if not serial:
        serial = str(await _auto_serial_number(db, ENTITY_OOT_LEDGER))
        payload["serial_number"] = serial
    fields = _build_ledger_feishu_fields(payload)
    created = await _create_entity_record(db, ENTITY_OOT_LEDGER, fields)
    return await get_oot_ledger_record(db, created["record_id"])


async def update_oot_ledger_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_oot_ledger_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_ledger_feishu_fields(merged)
    await _update_entity_record(db, ENTITY_OOT_LEDGER, record_id, fields)
    return await get_oot_ledger_record(db, record_id)


async def delete_oot_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_OOT_LEDGER, record_id)


async def pull_oot_ledger_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_OOT_LEDGER, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_oot_ledger_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


# ============ Product Department ============

ENTITY_OOS_OOT_PRODUCT_DEPARTMENT = "oos_oot_product_department"


def _map_product_department(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    fields = record.get("fields") or {}
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    modified_at = feishu_sync_service._get_record_modified_at(record)

    return {
        "record_id": str(record.get("record_id") or ""),
        "serial_number": normalize_text(field_value(entity, fields, "序号")),
        "product_code": normalize_text(field_value(entity, fields, "产品代码")),
        "fermentation_department": normalize_text(
            field_value(entity, fields, "涉及发酵部门")
        ),
        "fermentation_head": _map_nested_user(
            field_value(entity, fields, "涉及发酵部门负责人")
        ),
        "extraction_department": normalize_text(
            field_value(entity, fields, "涉及提炼部门")
        ),
        "extraction_head": _map_nested_user(
            field_value(entity, fields, "涉及提炼部门负责人")
        ),
        "updated_at": modified_at or datetime.now(UTC),
    }


async def list_product_department_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT)
    items = [_map_product_department(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f)) or "").lower()
                for f in (
                    "serial_number",
                    "product_code",
                    "fermentation_department",
                    "extraction_department",
                )
            )
        ]

    items.sort(key=lambda x: x.get("serial_number") or "", reverse=False)
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_product_department_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_product_department(record, entity)
    raise NotFoundException(resource="产品涉及部门记录")


def _build_product_department_feishu_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for feishu_key, payload_key in (
        ("序号", "serial_number"),
        ("产品代码", "product_code"),
        ("涉及发酵部门", "fermentation_department"),
        ("涉及提炼部门", "extraction_department"),
    ):
        val = (payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    # User fields - resolve by name from department contacts or direct open_id
    for feishu_key, payload_key in (
        ("涉及发酵部门负责人", "fermentation_head"),
        ("涉及提炼部门负责人", "extraction_head"),
    ):
        val = payload.get(payload_key)
        if val:
            if isinstance(val, dict) and val.get("id"):
                fields[feishu_key] = [val]
            elif isinstance(val, str) and val.strip():
                fields[feishu_key] = [{"id": val.strip()}]
    return fields


async def create_product_department_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    fields = _build_product_department_feishu_fields(payload)
    created = await _create_entity_record(db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, fields)
    return await get_product_department_record(db, created["record_id"])


async def update_product_department_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_product_department_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_product_department_feishu_fields(merged)
    await _update_entity_record(
        db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, record_id, fields
    )
    return await get_product_department_record(db, record_id)


async def delete_product_department_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, record_id)


async def pull_product_department_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_OOS_OOT_PRODUCT_DEPARTMENT, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_product_department_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}
