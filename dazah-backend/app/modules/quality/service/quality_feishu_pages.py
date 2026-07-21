from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality import repository
from app.modules.quality.models import ChangeControl
from app.modules.quality.service import (
    quality_feishu_sync as feishu_sync_service,
    quality_management as quality_management_service,
    tracking_records as tracking_service,
)
from app.platform.integrations.feishu.utils import build_bitable_client


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


def _contains_text(value: str | None, keyword: str | None) -> bool:
    if not keyword:
        return True
    return keyword.lower() in (value or "").lower()


def _normalize_yes_no(value: Any) -> str:
    normalized = feishu_sync_service._normalize_bool_from_yes_no(value)
    if normalized is True:
        return "是"
    if normalized is False:
        return "否"
    return ""


def _split_related_capa_codes(value: str | None) -> list[str] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("，", "、").replace(",", "、").replace("/", "、")
    items = [part.strip() for part in normalized.split("、") if part.strip()]
    return items or None


def _parse_datetime_like(value: Any) -> datetime | None:
    return feishu_sync_service._parse_feishu_datetime(value)


def _normalize_closed_status(value: Any) -> str:
    return "closed" if feishu_sync_service._normalize_bool_from_yes_no(value) else "draft"


def _serialize_report_record_alias(item: dict[str, Any]) -> dict[str, Any]:
    next_item = dict(item)
    next_item["record_id"] = (
        next_item.get("record_id")
        or next_item.get("feishu_base_record_id")
        or next_item.get("id")
    )
    return next_item


def _serialize_investigation_record_alias(item: dict[str, Any]) -> dict[str, Any]:
    next_item = dict(item)
    next_item["record_id"] = (
        next_item.get("record_id")
        or next_item.get("feishu_base_record_id")
        or next_item.get("id")
    )
    return next_item


async def _resolve_runtime_entity(
    db: AsyncSession,
    entity_code: str,
    *,
    direction: str,
) -> tuple[feishu_sync_service.QualityFeishuRuntimeConfig, feishu_sync_service.QualityFeishuEntityRuntimeConfig]:
    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(entity_code, direction=direction)
    if not runtime.is_enabled() or not entity or not entity.app_token or not entity.table_id:
        raise ValueError(f"{entity_code} 飞书 Base 未启用")
    return runtime, entity


async def _search_entity_records(
    db: AsyncSession,
    entity_code: str,
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    filter_str = None
    if filters:
        conditions = [
            (str(key), str(value))
            for key, value in filters.items()
            if value not in (None, "", [])
        ]
        if conditions:
            runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
            entity = runtime.get_entity_config(entity_code, direction="pull")
            filter_str = feishu_sync_service._build_search_filter(entity, conditions)
    return await feishu_sync_service.feishu_sync.search_records(
        db,
        entity_code,
        None,
        filter_str=filter_str,
    )


async def _create_entity_record(
    db: AsyncSession,
    entity_code: str,
    fields: dict[str, Any],
    *,
    search_conditions: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    record_id, table_id = await feishu_sync_service.feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=search_conditions,
    )
    return {"record_id": record_id, "table_id": table_id}


async def _update_entity_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    search_conditions: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    next_record_id, table_id = await feishu_sync_service.feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        record_id,
        fields,
        search_conditions=search_conditions,
    )
    return {"record_id": next_record_id, "table_id": table_id}


async def _delete_entity_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> None:
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
    client = build_bitable_client(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    await client.delete_record(entity.table_id, record_id)


def _map_deviation_ledger_base_item(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    fields = record.get("fields") or {}
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    modified_at = feishu_sync_service._get_record_modified_at(record)
    created_at = parse_datetime(record.get("created_time")) or modified_at or datetime.now(UTC)

    deviation_code = normalize_text(field_value(entity, fields, "偏差编号")) or ""
    description = normalize_text(field_value(entity, fields, "偏差简要描述"))
    has_occurred_before = feishu_sync_service._normalize_bool_from_yes_no(
        field_value(entity, fields, "偏差是否曾发生")
    )
    investigation_completed_at = parse_datetime(
        field_value(entity, fields, "调查完成时间")
    )
    close_time = parse_datetime(field_value(entity, fields, "关闭时间"))
    related_capa_codes = _split_related_capa_codes(
        normalize_text(field_value(entity, fields, "关联capa"))
    )

    return {
        "id": str(record.get("record_id") or ""),
        "record_id": str(record.get("record_id") or ""),
        "deviation_code": deviation_code,
        "final_code": None,
        "title": description or deviation_code,
        "department": None,
        "discovery_date": None,
        "discovery_time": None,
        "status": _normalize_closed_status(field_value(entity, fields, "是否关闭")),
        "level": normalize_text(field_value(entity, fields, "偏差等级")),
        "root_cause_category": None,
        "reporter_id": None,
        "handler": None,
        "batch_number": None,
        "affected_items": normalize_text(field_value(entity, fields, "产品名称/批号")),
        "description": description,
        "has_occurred_before": has_occurred_before,
        "material_disposition": normalize_text(
            field_value(entity, fields, "产品/物料处理结果")
        ),
        "corrective_actions": normalize_text(
            field_value(entity, fields, "纠正预防措施")
        ),
        "root_cause_analysis": normalize_text(field_value(entity, fields, "根本原因")),
        "investigation_completed_at": investigation_completed_at,
        "close_time": close_time,
        "related_capa_codes": related_capa_codes,
        "related_capas": None,
        "feishu_base_table_id": entity.table_id,
        "feishu_base_record_id": str(record.get("record_id") or ""),
        "feishu_sync_status": "synced",
        "feishu_last_sync_error": None,
        "feishu_last_sync_direction": "base_to_system",
        "feishu_synced_at": modified_at,
        "feishu_source_updated_at": modified_at,
        "status_updated_at": close_time,
        "returned_step": None,
        "created_at": created_at,
    }


def _map_deviation_ledger_detail_item(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    item = _map_deviation_ledger_base_item(record, entity)
    item.update(
        {
            "discovery_location": None,
            "immediate_actions": None,
            "discoverer": None,
            "ai_analysis": None,
            "investigation_records": None,
            "review_opinions": None,
            "attachments": None,
            "needs_cross_dept_review": None,
            "cross_dept_reviewers": None,
            "report_content": None,
            "report_versions": None,
            "updated_at": item["feishu_source_updated_at"] or item["created_at"],
        }
    )
    return item


def _build_deviation_ledger_fields(
    payload: dict[str, Any],
    *,
    deviation_code: str,
) -> dict[str, Any]:
    affected_items = (payload.get("affected_items") or "").strip()
    batch_number = (payload.get("batch_number") or "").strip()
    product_batch = (payload.get("product_batch") or "").strip()
    combined_product_batch = product_batch or feishu_sync_service._join_non_empty(
        [affected_items or None, batch_number or None]
    )

    is_closed = payload.get("is_closed")
    if is_closed is None and payload.get("status") is not None:
        is_closed = str(payload.get("status")).strip().lower() == "closed"

    return {
        "偏差编号": deviation_code,
        "产品名称/批号": combined_product_batch or "",
        "偏差简要描述": (payload.get("description") or payload.get("title") or "").strip(),
        "偏差是否曾发生": _normalize_yes_no(payload.get("has_occurred_before")),
        "根本原因": (payload.get("root_cause_analysis") or "").strip(),
        "偏差等级": (payload.get("level") or "").strip(),
        "调查完成时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("investigation_completed_at"))
        ),
        "纠正预防措施": (payload.get("corrective_actions") or "").strip(),
        "产品/物料处理结果": (payload.get("material_disposition") or "").strip(),
        "是否关闭": _normalize_yes_no(is_closed),
        "关闭时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("close_time"))
        ),
    }


async def _get_investigation_push_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, item, _ = await tracking_service._get_deviation_investigation_push_record_from_feishu(
        db,
        record_id,
    )
    return _serialize_investigation_record_alias(item)


async def list_report_records(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    result = await quality_management_service.get_deviation_report_record_list(
        db,
        page=page,
        page_size=page_size,
    )
    result["items"] = [_serialize_report_record_alias(item) for item in result["items"]]
    return result


async def list_investigation_push_records(
    db: AsyncSession,
    *,
    deviation_id: str | None = None,
    deviation_code: str | None = None,
    push_round: str | None = None,
    submitter: str | None = None,
    department_head_result: str | None = None,
    qa_result: str | None = None,
    qa_head_result: str | None = None,
    submitted_at_from: str | None = None,
    submitted_at_to: str | None = None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    result = await tracking_service.get_deviation_investigation_push_record_list(
        db,
        deviation_id=deviation_id,
        deviation_code=deviation_code,
        push_round=push_round,
        submitter=submitter,
        department_head_result=department_head_result,
        qa_result=qa_result,
        qa_head_result=qa_head_result,
        submitted_at_from=submitted_at_from,
        submitted_at_to=submitted_at_to,
        page=page,
        page_size=page_size,
    )
    result["items"] = [
        _serialize_investigation_record_alias(item) for item in result["items"]
    ]
    return result


async def create_investigation_push_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    fields, deviation_code, push_round = await _build_investigation_push_fields(
        db,
        payload,
    )
    created = await _create_entity_record(
        db,
        "deviation_investigation_push_record",
        fields,
        search_conditions=[("偏差编号", deviation_code), ("第N次推送", push_round)],
    )
    return await _get_investigation_push_record(db, created["record_id"])


async def _build_investigation_push_fields(
    db: AsyncSession,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    deviation_code = str(payload.get("deviation_code") or "").strip()
    deviation_id = payload.get("deviation_id")
    if not deviation_code and deviation_id:
        deviation = await repository.get_deviation_by_id(db, deviation_id)
        if not deviation:
            raise ValueError(f"Deviation {deviation_id} not found")
        deviation_code = deviation.deviation_code
    if not deviation_code:
        raise ValueError("偏差编号不能为空")

    push_round = str(payload.get("push_round") or "").strip()
    if not push_round:
        raise ValueError("第N次推送不能为空")

    submitter_name = str(payload.get("submitter") or "").strip() or None
    department_head = str(payload.get("department_head") or "").strip() or None
    department = str(payload.get("department") or "").strip() or None
    submitter_open_id = str(payload.get("submitter_open_id") or "").strip() or None
    if submitter_open_id:
        submitter_contact = await tracking_service._resolve_selected_submitter_contact(
            db,
            submitter_open_id,
        )
        submitter_name = submitter_name or submitter_contact.get("name") or None
        department_head = (
            department_head or submitter_contact.get("department_head_name") or None
        )
        department = submitter_contact.get("department") or None

    if not department:
        deviation = await repository.get_deviation_by_code(db, deviation_code)
        department = deviation.department if deviation else None

    fields = {
        "偏差编号": deviation_code,
        "第N次推送": push_round,
        "偏差调查报告": feishu_sync_service._to_feishu_url_field_value(
            payload.get("investigation_report_url")
        ),
        "提交日期": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("submitted_at")) or datetime.now(UTC)
        ),
        "提交人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            submitter_name,
            department=department,
        ),
        "部门负责人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            department_head,
            department=department,
        ),
        "部门负责人审核结果": feishu_sync_service._to_feishu_review_option(
            payload.get("department_head_result")
        ),
        "部门负责人审核时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("department_head_reviewed_at"))
        ),
        "QA": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            payload.get("qa_name"),
        ),
        "QA审核结果": feishu_sync_service._to_feishu_review_option(
            payload.get("qa_result")
        ),
        "QA审核时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("qa_reviewed_at"))
        ),
        "QA负责人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            payload.get("qa_head_name"),
        ),
        "QA负责人审核结果": feishu_sync_service._to_feishu_review_option(
            payload.get("qa_head_result")
        ),
        "QA负责人审核时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("qa_head_reviewed_at"))
        ),
    }
    return fields, deviation_code, push_round


async def update_investigation_push_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await _get_investigation_push_record(db, record_id)
    merged = {**current, **payload}
    fields, deviation_code, push_round = await _build_investigation_push_fields(
        db,
        merged,
    )
    updated = await _update_entity_record(
        db,
        "deviation_investigation_push_record",
        record_id,
        fields,
        search_conditions=[("偏差编号", deviation_code), ("第N次推送", push_round)],
    )
    return await _get_investigation_push_record(db, updated["record_id"])


async def delete_investigation_push_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _get_investigation_push_record(db, record_id)
    await _delete_entity_record(db, "deviation_investigation_push_record", record_id)


async def list_deviation_ledger_records(
    db: AsyncSession,
    *,
    record_ids: list[str] | None = None,
    keyword: str | None = None,
    deviation_code: str | None = None,
    product_keyword: str | None = None,
    has_occurred_before: bool | None = None,
    is_closed: bool | None = None,
    investigation_completed_from: str | None = None,
    investigation_completed_to: str | None = None,
    root_cause_keyword: str | None = None,
    corrective_actions_keyword: str | None = None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, "deviation_ledger", direction="pull")
    records = await _search_entity_records(db, "deviation_ledger")
    items = [_map_deviation_ledger_base_item(record, entity) for record in records]
    record_id_set = {record_id.strip() for record_id in (record_ids or []) if record_id.strip()}

    investigation_from_dt = _parse_datetime_like(investigation_completed_from)
    investigation_to_dt = _parse_datetime_like(investigation_completed_to)

    filtered: list[dict[str, Any]] = []
    for item in items:
        if record_id_set and str(item.get("record_id") or "") not in record_id_set:
            continue
        if keyword and not any(
            _contains_text(item.get(field), keyword)
            for field in ("deviation_code", "title", "description")
        ):
            continue
        if deviation_code and not _contains_text(item.get("deviation_code"), deviation_code):
            continue
        if product_keyword and not any(
            _contains_text(item.get(field), product_keyword)
            for field in ("affected_items", "batch_number")
        ):
            continue
        if has_occurred_before is not None and item.get("has_occurred_before") != has_occurred_before:
            continue
        if is_closed is not None and ((item.get("status") == "closed") != is_closed):
            continue
        if root_cause_keyword and not _contains_text(
            item.get("root_cause_analysis"),
            root_cause_keyword,
        ):
            continue
        if corrective_actions_keyword and not _contains_text(
            item.get("corrective_actions"),
            corrective_actions_keyword,
        ):
            continue
        if investigation_from_dt and (
            item.get("investigation_completed_at") is None
            or item["investigation_completed_at"] < investigation_from_dt
        ):
            continue
        if investigation_to_dt and (
            item.get("investigation_completed_at") is None
            or item["investigation_completed_at"] >= investigation_to_dt
        ):
            continue
        filtered.append(item)

    filtered.sort(
        key=lambda item: item.get("feishu_source_updated_at") or item.get("created_at"),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(filtered[start:end], len(filtered), page, page_size)


async def get_deviation_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, "deviation_ledger", direction="pull")
    records = await _search_entity_records(db, "deviation_ledger")
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_deviation_ledger_detail_item(record, entity)
    raise ValueError("飞书偏差台账记录不存在")


async def create_deviation_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    deviation_code = str(payload.get("deviation_code") or "").strip()
    if not deviation_code:
        deviation_code = await quality_management_service._generate_monthly_deviation_code(
            db,
            datetime.now(UTC),
        )
    fields = _build_deviation_ledger_fields(payload, deviation_code=deviation_code)
    created = await _create_entity_record(
        db,
        "deviation_ledger",
        fields,
        search_conditions=[("偏差编号", deviation_code)],
    )
    return await get_deviation_ledger_record(db, created["record_id"])


async def update_deviation_ledger_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_deviation_ledger_record(db, record_id)
    merged = {**current, **payload}
    deviation_code = str(merged.get("deviation_code") or "").strip()
    if not deviation_code:
        raise ValueError("飞书偏差台账记录缺少偏差编号")
    fields = _build_deviation_ledger_fields(merged, deviation_code=deviation_code)
    await _update_entity_record(
        db,
        "deviation_ledger",
        record_id,
        fields,
        search_conditions=[("偏差编号", deviation_code)],
    )
    return await get_deviation_ledger_record(db, record_id)


async def delete_deviation_ledger_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, "deviation_ledger", record_id)


# ============ Change Ledger (变更管理) Feishu Sync ============


def _build_change_feishu_fields(change: ChangeControl) -> dict[str, Any]:
    """Map a local ChangeControl instance to Feishu Bitable change_ledger fields."""
    fields: dict[str, Any] = {
        "序号": change.serial_number or "",
        "变更控制号": change.change_code or "",
        "变更申请部门": change.applicant_department or "",
        "变更对象": change.change_object or "",
        "变更内容": change.change_content or "",
        "变更等级": change.change_level or "",
    }
    for feishu_field, local_date in (
        ("变更申请日期", change.application_date),
        ("变更计划批准日期", change.planned_approval_date),
        ("变更正式执行日期", change.execution_date),
        ("变更关闭日期", change.closure_date),
    ):
        fields[feishu_field] = feishu_sync_service._to_ms_timestamp(local_date)
    return fields


async def _find_change_feishu_record_id(
    db: AsyncSession,
    change_code: str,
) -> str | None:
    """Search Feishu change_ledger table for a record matching the given change_code.

    Returns the feishu record_id if found, otherwise None.
    The ValueError raised by _search_entity_records when the entity is not
    configured is caught and returns None.
    """
    normalize_text = feishu_sync_service._normalize_text
    try:
        records = await _search_entity_records(
            db,
            "change_ledger",
            filters={"变更控制号": change_code},
        )
    except ValueError:
        return None
    except Exception:
        records = await _search_entity_records(db, "change_ledger")
    if records:
        for record in records:
            fields = record.get("fields") or {}
            if normalize_text(fields.get("变更控制号")) == change_code:
                return str(record.get("record_id") or "")
    return None


async def sync_change_to_feishu(
    db: AsyncSession,
    change: ChangeControl,
) -> dict[str, Any]:
    """Push (create or update) a single ChangeControl record to Feishu Bitable.

    Searches by change_code; if a matching Feishu record exists it is updated,
    otherwise a new record is created.
    """
    fields = _build_change_feishu_fields(change)
    existing_id = await _find_change_feishu_record_id(db, change.change_code)
    if existing_id:
        return await _update_entity_record(
            db,
            "change_ledger",
            existing_id,
            fields,
            search_conditions=[("变更控制号", change.change_code)],
        )
    return await _create_entity_record(
        db,
        "change_ledger",
        fields,
        search_conditions=[("变更控制号", change.change_code)],
    )


async def delete_change_from_feishu(
    db: AsyncSession,
    change_code: str,
) -> bool:
    """Delete the Feishu change_ledger record matching the given change_code.

    Returns True if a record was found and deleted, False otherwise.
    """
    record_id = await _find_change_feishu_record_id(db, change_code)
    if not record_id:
        return False
    await _delete_entity_record(db, "change_ledger", record_id)
    return True


async def sync_changes_from_feishu(db: AsyncSession) -> dict[str, int]:
    """Pull all records from the Feishu Bitable change_ledger table and
    upsert them into the local ChangeControl table.

    Each Feishu record is matched by change_code:
    - If a local record with the same change_code exists, it is updated.
    - Otherwise a new ChangeControl row is created.

    Returns ``{"synced": N, "failed": N}``.
    """
    synced = 0
    failed = 0

    try:
        _, _entity = await _resolve_runtime_entity(db, "change_ledger", direction="pull")
    except ValueError:
        return {"synced": 0, "failed": 0}

    try:
        records = await _search_entity_records(db, "change_ledger")
    except Exception:
        return {"synced": 0, "failed": 0}

    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime

    for record in records:
        try:
            fields = record.get("fields") or {}

            change_code = normalize_text(fields.get("变更控制号"))
            if not change_code:
                failed += 1
                continue

            serial_number = normalize_text(fields.get("序号"))
            applicant_department = normalize_text(fields.get("变更申请部门"))
            change_object = normalize_text(fields.get("变更对象"))
            change_content = normalize_text(fields.get("变更内容"))
            change_level = normalize_text(fields.get("变更等级"))

            application_date = parse_datetime(fields.get("变更申请日期"))
            planned_approval_date = parse_datetime(fields.get("变更计划批准日期"))
            execution_date = parse_datetime(fields.get("变更正式执行日期"))
            closure_date = parse_datetime(fields.get("变更关闭日期"))

            result = await db.execute(
                select(ChangeControl).where(
                    ChangeControl.change_code == change_code,
                    ChangeControl.is_deleted == False,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.serial_number = serial_number
                existing.applicant_department = applicant_department
                existing.change_object = change_object
                existing.change_content = change_content
                existing.change_level = change_level
                existing.application_date = application_date.date() if application_date else None
                existing.planned_approval_date = planned_approval_date.date() if planned_approval_date else None
                existing.execution_date = execution_date.date() if execution_date else None
                existing.closure_date = closure_date.date() if closure_date else None
                existing.updated_at = datetime.now(UTC)
            else:
                change = ChangeControl(
                    serial_number=serial_number,
                    change_code=change_code,
                    applicant_department=applicant_department,
                    change_object=change_object,
                    change_content=change_content,
                    change_level=change_level,
                    application_date=application_date.date() if application_date else None,
                    planned_approval_date=planned_approval_date.date() if planned_approval_date else None,
                    execution_date=execution_date.date() if execution_date else None,
                    closure_date=closure_date.date() if closure_date else None,
                )
                db.add(change)

            await db.commit()
            synced += 1
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            failed += 1

    return {"synced": synced, "failed": failed}


# ============ Validation (验证与确认) Feishu Sync ============

VALIDATION_TYPE_ENTITY_MAP: dict[str, str] = {
    "equipment_qualification": "validation_equipment_qualification",
    "process_validation": "validation_process",
    "cleaning_validation": "validation_cleaning",
    "other_validation": "validation_other",
}

# 飞书验证类别中文 → 英文代码映射
VALIDATION_TYPE_FEISHU_TO_CODE: dict[str, str] = {
    "设备确认": "equipment_qualification",
    "工艺验证": "process_validation",
    "清洁验证": "cleaning_validation",
}

# 英文代码 → 飞书验证类别中文
VALIDATION_TYPE_CODE_TO_FEISHU: dict[str, str] = {
    "equipment_qualification": "设备确认",
    "process_validation": "工艺验证",
    "cleaning_validation": "清洁验证",
}


def _entity_code_for_validation_type(validation_type: str) -> str:
    return VALIDATION_TYPE_ENTITY_MAP.get(validation_type, "validation_master_plan")


async def _get_department_contacts_cache(db: AsyncSession) -> list[dict[str, Any]]:
    """获取部门联系人缓存（从飞书拉取）"""
    from app.modules.quality.service import quality_management as quality_management_service
    result = await quality_management_service.get_department_contact_list_from_feishu(
        db, page=1, page_size=1000
    )
    return result.get("items", [])


def _resolve_bitable_user_ids_from_names(
    contacts: list[dict[str, Any]],
    names_str: str | None,
) -> list[str] | None:
    """根据中文姓名从部门联系人中查找 bitable_user_id，必要时回退到 open_id。"""
    if not names_str:
        return None
    name_list = [n.strip() for n in names_str.split("、") if n.strip()]
    if not name_list:
        return None
    user_ids: list[str] = []
    for name in name_list:
        for contact in contacts:
            contact_name = str(contact.get("name") or "").strip()
            if contact_name == name:
                bitable_user_id = str(contact.get("bitable_user_id") or "").strip()
                open_id = str(contact.get("open_id") or "").strip()
                resolved_user_id = bitable_user_id or open_id
                if resolved_user_id:
                    user_ids.append(resolved_user_id)
                    break
    return user_ids if user_ids else None


def _translate_validation_type_f2c(feishu_type: str) -> str:
    """飞书中文验证类别 → 英文代码，不认识的归为 other_validation"""
    return VALIDATION_TYPE_FEISHU_TO_CODE.get(feishu_type, "other_validation")


def _translate_validation_type_c2f(code: str) -> str:
    """英文代码 → 飞书中文验证类别"""
    return VALIDATION_TYPE_CODE_TO_FEISHU.get(code, code)


def _parse_feishu_text_field(value: Any) -> str | None:
    """专门解析飞书文本字段（支持普通文本和 [{'text': 'xxx'}] 格式）"""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                t = item.get("text", "")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return " / ".join(parts) if parts else None
    if isinstance(value, dict):
        t = value.get("text", "")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return str(value).strip() or None


def _parse_validation_month_or_date(value: Any) -> date | None:
    text = _parse_feishu_text_field(value)
    if not text:
        return None
    normalized = text.strip().replace("年", "-").replace("月", "").replace(".", "-")
    parts = [part for part in normalized.split("-") if part]
    try:
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 1 and len(parts[0]) == 6 and parts[0].isdigit():
            return date(int(parts[0][:4]), int(parts[0][4:]), 1)
    except ValueError:
        return None
    return None


def _map_validation_base_item(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Map a Feishu bitable record to a validation item dict."""
    fields = record.get("fields") or {}
    normalize_text = feishu_sync_service._normalize_text
    parse_date = _parse_datetime_like
    modified_at = feishu_sync_service._get_record_modified_at(record)

    product_codes_raw = fields.get("产品代码")
    product_codes: list[str] | None = None
    if isinstance(product_codes_raw, list):
        product_codes = [str(item).strip() for item in product_codes_raw if str(item).strip()]
    elif isinstance(product_codes_raw, str) and product_codes_raw.strip():
        product_codes = [product_codes_raw.strip()]

    feishu_val_type = _parse_feishu_text_field(fields.get("验证类别")) or ""
    validation_type = _translate_validation_type_f2c(feishu_val_type)

    drafted_date = parse_date(fields.get("起草时间"))
    approved_date = parse_date(fields.get("批准时间"))
    drafted_date_1 = parse_date(fields.get("报告起草时间"))
    approved_date_1 = parse_date(fields.get("报告批准时间"))
    # 验证到期时间是文本字段（如 "2026.02"），不是日期
    planned_end_text = _parse_feishu_text_field(fields.get("验证到期时间"))

    revalidation_years_raw = _parse_feishu_text_field(fields.get("再验证周期（几年）"))
    revalidation_years: int | None = None
    if revalidation_years_raw:
        digits = "".join(c for c in revalidation_years_raw if c.isdigit())
        if digits:
            revalidation_years = int(digits)

    # 人员字段是用户类型，提取名称列表
    participants_raw = fields.get("人员")
    participants: str | None = None
    if isinstance(participants_raw, list):
        names = []
        for item in participants_raw:
            if isinstance(item, dict):
                name = item.get("name", "") or item.get("text", "")
                if name:
                    names.append(name)
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        participants = "、".join(names) if names else None
    elif participants_raw:
        participants = normalize_text(participants_raw)

    # 负责人字段
    owner_raw = fields.get("负责人")
    owner_name: str | None = None
    if isinstance(owner_raw, list):
        owner_names = []
        for item in owner_raw:
            if isinstance(item, dict):
                name = item.get("name", "") or item.get("text", "")
                if name:
                    owner_names.append(name)
            elif isinstance(item, str) and item.strip():
                owner_names.append(item.strip())
        owner_name = "、".join(owner_names) if owner_names else None
    elif owner_raw:
        owner_name = normalize_text(owner_raw)

    return {
        "record_id": str(record.get("record_id") or ""),
        "table_id": None,
        "validation_type": validation_type,
        "record_code": "",  # 飞书表中无此字段
        "title": _parse_feishu_text_field(fields.get("确认名称")) or "",
        "status": normalize_text(fields.get("任务状态")),
        "department": normalize_text(fields.get("部门名称")),
        "equipment_code": _parse_feishu_text_field(fields.get("设备编码")),
        "product_codes": product_codes,
        "planned_end_date": planned_end_text,  # 文本格式如 "2026.02"
        "group_chat": normalize_text(fields.get("群组")),
        "participants": participants,
        "owner_name": owner_name,
        "plan_name": _parse_feishu_text_field(fields.get("方案名称")),
        "plan_code": _parse_feishu_text_field(fields.get("方案编码")),
        "drafted_at": drafted_date.date() if drafted_date else None,
        "approved_at": approved_date.date() if approved_date else None,
        "report_no": _parse_feishu_text_field(fields.get("报告编号")),
        "drafted_at_1": drafted_date_1.date() if drafted_date_1 else None,
        "approved_at_1": approved_date_1.date() if approved_date_1 else None,
        "revalidation_cycle_years": revalidation_years,
        "created_at": parse_date(record.get("created_time")) or datetime.now(UTC),
        "updated_at": modified_at or datetime.now(UTC),
    }


async def _build_validation_feishu_fields(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a dictionary of Feishu bitable fields from a validation payload."""
    fields: dict[str, Any] = {}

    # 验证类别：英文代码转中文
    vtype = payload.get("validation_type")
    if vtype:
        fields["验证类别"] = _translate_validation_type_c2f(str(vtype))

    # 确认名称
    title = payload.get("title")
    if title:
        fields["确认名称"] = str(title).strip()

    # 任务状态
    status = payload.get("status")
    if status is not None:
        fields["任务状态"] = str(status)

    # 部门名称
    dept = payload.get("department")
    if dept:
        fields["部门名称"] = str(dept).strip()

    # 设备编码
    equip = payload.get("equipment_code")
    if equip:
        fields["设备编码"] = str(equip).strip()

    # 产品代码
    prods = payload.get("product_codes")
    if prods:
        if isinstance(prods, list):
            fields["产品代码"] = prods
        else:
            fields["产品代码"] = [str(prods)]

    # 人员 和 负责人：优先通过部门联系人反查 bitable_user_id 写入飞书用户字段
    contacts = await _get_department_contacts_cache(db)
    participants = payload.get("participants")
    if participants and isinstance(participants, str) and participants.strip():
        participant_ids = _resolve_bitable_user_ids_from_names(contacts, participants)
        if participant_ids:
            fields["人员"] = [{"id": oid} for oid in participant_ids]

    owner = payload.get("owner_name")
    if owner and isinstance(owner, str) and owner.strip():
        owner_ids = _resolve_bitable_user_ids_from_names(contacts, owner)
        if owner_ids:
            fields["负责人"] = [{"id": oid} for oid in owner_ids[:1]]

    # 群组
    gc = payload.get("group_chat")
    if gc:
        fields["群组"] = str(gc).strip()

    # 方案名称
    pn = payload.get("plan_name")
    if pn:
        fields["方案名称"] = str(pn).strip()

    # 方案编码
    pc = payload.get("plan_code")
    if pc:
        fields["方案编码"] = str(pc).strip()

    # 报告编号
    rn = payload.get("report_no")
    if rn:
        fields["报告编号"] = str(rn).strip()

    # 日期时间字段
    for feishu_key, payload_key in (
        ("验证到期时间", "planned_end_date"),
        ("起草时间", "drafted_at"),
        ("批准时间", "approved_at"),
        ("报告起草时间", "drafted_at_1"),
        ("报告批准时间", "approved_at_1"),
    ):
        val = payload.get(payload_key)
        if val is not None:
            # 验证到期时间是文本，其他是日期
            if feishu_key == "验证到期时间":
                fields[feishu_key] = str(val).strip()
            else:
                fields[feishu_key] = feishu_sync_service._to_ms_timestamp(
                    _parse_datetime_like(val)
                )

    # 再验证周期
    rv = payload.get("revalidation_cycle_years")
    if rv is not None:
        try:
            years = int(rv)
            fields["再验证周期（几年）"] = f"{years}年"
        except (ValueError, TypeError):
            pass
    return fields


async def list_validation_records_from_feishu(
    db: AsyncSession,
    *,
    validation_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    record_code: str | None = None,
    department: str | None = None,
    planned_end_date_from: str | None = None,
    planned_end_date_to: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从飞书拉取验证记录列表。"""
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"

    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except ValueError:
        return _build_page_result([], 0, page, page_size)

    try:
        records = await _search_entity_records(db, entity_code)
    except Exception:
        return _build_page_result([], 0, page, page_size)

    items = [_map_validation_base_item(record) for record in records]

    # Filter by validation_type if specified (for child pages)
    if validation_type:
        vtype_to_match = validation_type
        items = [item for item in items if item.get("validation_type") == vtype_to_match]

    # Additional filters
    if status:
        items = [item for item in items if item.get("status") == status]
    if department:
        items = [item for item in items if item.get("department") == department]
    if record_code:
        items = [
            item
            for item in items
            if record_code.lower() in (item.get("record_code") or "").lower()
        ]
    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if kw in (item.get("title") or "").lower()
            or kw in (item.get("department") or "").lower()
            or kw in (item.get("plan_code") or "").lower()
            or kw in (item.get("plan_name") or "").lower()
            or kw in (item.get("equipment_code") or "").lower()
        ]

    planned_from = _parse_validation_month_or_date(planned_end_date_from)
    planned_to = _parse_validation_month_or_date(planned_end_date_to)
    if planned_from:
        items = [
            item
            for item in items
            if (planned_date := _parse_validation_month_or_date(item.get("planned_end_date")))
            and planned_date >= planned_from
        ]
    if planned_to:
        items = [
            item
            for item in items
            if (planned_date := _parse_validation_month_or_date(item.get("planned_end_date")))
            and planned_date <= planned_to
        ]

    drafted_from = _parse_validation_month_or_date(drafted_at_from)
    drafted_to = _parse_validation_month_or_date(drafted_at_to)
    if drafted_from:
        items = [
            item
            for item in items
            if (drafted_date := _parse_validation_month_or_date(item.get("drafted_at")))
            and drafted_date >= drafted_from
        ]
    if drafted_to:
        items = [
            item
            for item in items
            if (drafted_date := _parse_validation_month_or_date(item.get("drafted_at")))
            and drafted_date <= drafted_to
        ]

    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)
    start = (page - 1) * page_size
    return _build_page_result(items[start : start + page_size], len(items), page, page_size)


async def get_validation_record_from_feishu(
    db: AsyncSession,
    record_id: str,
    validation_type: str | None = None,
) -> dict[str, Any]:
    """从飞书获取单条验证记录详情。"""
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"

    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except ValueError:
        raise ValueError("验证与确认飞书 Base 未启用")

    records = await _search_entity_records(db, entity_code)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            return _map_validation_base_item(record)
    raise ValueError("飞书验证记录不存在")


async def create_validation_record_in_feishu(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """在飞书中创建验证记录。"""
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("确认名称不能为空")
    validation_type = str(payload.get("validation_type") or "").strip()
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"
    fields = await _build_validation_feishu_fields(db, payload)
    created = await _create_entity_record(
        db,
        entity_code,
        fields,
        search_conditions=[("确认名称", title)],
    )
    return await get_validation_record_from_feishu(db, created["record_id"], validation_type)


async def update_validation_record_in_feishu(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
    validation_type: str | None = None,
) -> dict[str, Any]:
    """更新飞书中的验证记录。"""
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"

    current = await get_validation_record_from_feishu(db, record_id, validation_type)
    merged = {**current, **payload}
    title = str(merged.get("title") or "").strip()
    if not title:
        raise ValueError("飞书验证记录缺少确认名称")

    fields = await _build_validation_feishu_fields(db, merged)
    await _update_entity_record(
        db,
        entity_code,
        record_id,
        fields,
        search_conditions=[("确认名称", title)],
    )
    return await get_validation_record_from_feishu(db, record_id, validation_type)


async def delete_validation_record_in_feishu(
    db: AsyncSession,
    record_id: str,
    validation_type: str | None = None,
) -> None:
    """删除飞书中的验证记录。"""
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"

    await _delete_entity_record(db, entity_code, record_id)


async def pull_validation_records_from_feishu(
    db: AsyncSession,
    validation_type: str | None = None,
) -> dict[str, int]:
    """从飞书拉取验证记录并返回拉取结果。"""
    entity_code = _entity_code_for_validation_type(validation_type) if validation_type else "validation_master_plan"

    try:
        _, _entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except ValueError:
        return {"synced": 0, "failed": 0}

    synced = 0
    failed = 0

    try:
        result = await list_validation_records_from_feishu(
            db,
            validation_type=validation_type,
            page=1,
            page_size=10000,
        )
    except Exception:
        return {"synced": 0, "failed": 0}
    synced = len(result.get("items", []))
    failed = 0
    return {"synced": synced, "failed": failed}
