"""Service layer for deviation investigation pushes and CAPA plan tracks."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality import repository
from app.modules.quality.schemas import (
    CapaPlanTrackDetail,
    CapaPlanTrackListItem,
    CreateCapaPlanTrackRequest,
    CreateDeviationInvestigationPushRecordRequest,
    DeviationInvestigationPushRecordDetail,
    DeviationInvestigationPushRecordListItem,
    UpdateCapaPlanTrackRequest,
    UpdateDeviationInvestigationPushRecordRequest,
)

logger = logging.getLogger(__name__)


def _build_page_result(
    items: list[dict[str, Any]], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _serialize_capa_plan_track_items(items: list[Any]) -> list[dict[str, Any]]:
    item_dicts: list[dict[str, Any]] = []
    for item in items:
        item_dict = CapaPlanTrackListItem.model_validate(item).model_dump()
        item_dict["linked_capa_code"] = item.capa_code
        item_dicts.append(item_dict)
    return item_dicts


def _parse_date_filter(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime_filter(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_datetime_filter_end_exclusive(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value) + timedelta(days=1)


def _contains_text(value: str | None, keyword: str | None) -> bool:
    if not keyword:
        return True
    return keyword.lower() in (value or "").lower()


def _get_record_created_at(record: dict[str, Any]) -> datetime | None:
    value = record.get("created_time")
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _extract_feishu_link(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        for item in value:
            extracted = _extract_feishu_link(item)
            if extracted:
                return extracted
        return None
    if isinstance(value, dict):
        for key in ("link", "url", "href", "value", "text", "name"):
            if key in value:
                extracted = _extract_feishu_link(value[key])
                if extracted:
                    return extracted
        return None
    return str(value).strip() or None


def _to_feishu_url_field(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized
    raise ValueError("偏差调查报告必须填写有效链接")


async def _resolve_selected_submitter_contact(
    db: AsyncSession, submitter_open_id: str | None
) -> dict[str, str]:
    normalized_open_id = (submitter_open_id or "").strip()
    if not normalized_open_id:
        raise AppException(message="提交人不能为空")

    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu,
    )

    result = await get_department_contact_list_from_feishu(db, page=1, page_size=1000)
    for contact in result.get("items", []):
        if str(contact.get("open_id") or "").strip() == normalized_open_id:
            return {
                "name": str(contact.get("name") or "").strip(),
                "open_id": normalized_open_id,
                "department": str(contact.get("department") or "").strip(),
                "department_head_name": str(
                    contact.get("department_head_name") or ""
                ).strip(),
            }

    raise AppException(message="所选提交人不存在于部门联系人台账中")


async def _build_deviation_investigation_push_items_from_feishu(
    db: AsyncSession,
    *,
    deviation_id: uuid.UUID | None = None,
    deviation_code: str | None = None,
    push_round: str | None = None,
    submitter: str | None = None,
    department_head_result: str | None = None,
    qa_result: str | None = None,
    qa_head_result: str | None = None,
    submitted_at_from: datetime | None = None,
    submitted_at_to: datetime | None = None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(
        "deviation_investigation_push_record", direction="pull"
    )
    if not runtime.is_enabled() or not entity:
        return _build_page_result([], 0, page, page_size)

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_investigation_push_record",
        None,
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    normalize_review_result = feishu_sync_service._normalize_review_result
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    deviation_codes = []
    for record in records:
        code = normalize_text(
            field_value(entity, record.get("fields") or {}, "偏差编号")
        )
        if code:
            deviation_codes.append(code)

    items: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        current_deviation_code = (
            normalize_text(field_value(entity, fields, "偏差编号")) or ""
        )
        current_push_round = (
            normalize_text(field_value(entity, fields, "第N次推送")) or "第1次"
        )
        submitted_at_value = parse_datetime(field_value(entity, fields, "提交日期"))
        linked_deviation = (
            await repository.get_deviation_by_code(db, current_deviation_code)
            if current_deviation_code
            else None
        )
        item = DeviationInvestigationPushRecordListItem(
            id=record.get("record_id", ""),
            local_record_id=None,
            deviation_id=linked_deviation.id if linked_deviation else None,
            deviation_code=current_deviation_code,
            push_round=current_push_round,
            investigation_report_url=_extract_feishu_link(
                field_value(entity, fields, "偏差调查报告")
            ),
            submitted_at=submitted_at_value,
            submitter=normalize_text(field_value(entity, fields, "提交人")),
            submitters=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "提交人")
            ),
            department_head=normalize_text(field_value(entity, fields, "部门负责人")),
            department_heads=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "部门负责人")
            ),
            department_head_result=normalize_review_result(
                field_value(entity, fields, "部门负责人审核结果")
            ),
            department_head_reviewed_at=parse_datetime(
                field_value(entity, fields, "部门负责人审核时间")
            ),
            qa_name=normalize_text(field_value(entity, fields, "QA")),
            qas=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA")
            ),
            qa_result=normalize_review_result(
                field_value(entity, fields, "QA审核结果")
            ),
            qa_reviewed_at=parse_datetime(field_value(entity, fields, "QA审核时间")),
            qa_head_name=normalize_text(field_value(entity, fields, "QA负责人")),
            qa_heads=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA负责人")
            ),
            qa_head_result=normalize_review_result(
                field_value(entity, fields, "QA负责人审核结果")
            ),
            qa_head_reviewed_at=parse_datetime(
                field_value(entity, fields, "QA负责人审核时间")
            ),
            feishu_base_table_id=entity.table_id,
            feishu_base_record_id=record.get("record_id"),
            feishu_sync_status="synced",
            feishu_last_sync_error=None,
            feishu_last_sync_direction="base_to_system",
            feishu_synced_at=get_record_modified_at(record),
            feishu_source_updated_at=get_record_modified_at(record),
            created_at=_get_record_created_at(record) or get_record_modified_at(record),
            updated_at=get_record_modified_at(record),
        ).model_dump()

        if deviation_id and item.get("deviation_id") != deviation_id:
            continue
        if deviation_code and not _contains_text(
            item.get("deviation_code"), deviation_code
        ):
            continue
        if push_round and item.get("push_round") != push_round:
            continue
        if submitter and not _contains_text(item.get("submitter"), submitter):
            continue
        if (
            department_head_result
            and item.get("department_head_result") != department_head_result
        ):
            continue
        if qa_result and item.get("qa_result") != qa_result:
            continue
        if qa_head_result and item.get("qa_head_result") != qa_head_result:
            continue
        if submitted_at_from and (
            item.get("submitted_at") is None or item["submitted_at"] < submitted_at_from
        ):
            continue
        if submitted_at_to and (
            item.get("submitted_at") is None or item["submitted_at"] >= submitted_at_to
        ):
            continue
        items.append(item)

    items.sort(
        key=lambda item: (
            item.get("submitted_at") or datetime.min.replace(tzinfo=UTC),
            item.get("feishu_source_updated_at") or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def get_deviation_report_record_from_feishu(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("deviation_report_record", direction="pull")
    if not runtime.is_enabled() or not entity:
        raise AppException(message="飞书报告记录未启用")

    records = await feishu_sync_service.feishu_sync.search_records(
        db, "deviation_report_record", None
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    for record in records:
        if str(record.get("record_id") or "") != record_id:
            continue
        fields = record.get("fields") or {}
        modified_at = get_record_modified_at(record)
        created_at = parse_datetime(record.get("created_time")) or modified_at
        return {
            "deviation_code": normalize_text(field_value(entity, fields, "偏差编号")),
            "description": normalize_text(field_value(entity, fields, "偏差内容")),
            "report_time": parse_datetime(field_value(entity, fields, "报告时间")),
            "product_batch": normalize_text(
                field_value(entity, fields, "涉及产品名称/批号")
            ),
            "department": normalize_text(field_value(entity, fields, "部门")),
            "reporter_name": normalize_text(field_value(entity, fields, "报告人")),
            "reporters": feishu_sync_service._parse_person_field(
                field_value(entity, fields, "报告人")
            ),
            "department_head": normalize_text(
                field_value(entity, fields, "部门负责人")
            ),
            "department_heads": feishu_sync_service._parse_person_field(
                field_value(entity, fields, "部门负责人")
            ),
            "department_head_result": _normalize_checkbox_result(
                field_value(entity, fields, "部门负责人确认")
            ),
            "department_head_reviewed_at": parse_datetime(
                field_value(entity, fields, "部门负责人确认时间")
            ),
            "qa_name": normalize_text(field_value(entity, fields, "QA")),
            "qas": feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA")
            ),
            "qa_result": _normalize_checkbox_result(
                field_value(entity, fields, "QA确认")
            ),
            "qa_reviewed_at": parse_datetime(field_value(entity, fields, "QA确认时间")),
            "qa_head_name": normalize_text(field_value(entity, fields, "QA负责人")),
            "qa_heads": feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA负责人")
            ),
            "qa_head_result": _normalize_checkbox_result(
                field_value(entity, fields, "QA负责人确认")
            ),
            "qa_head_reviewed_at": parse_datetime(
                field_value(entity, fields, "QA负责人确认时间")
            ),
            "report_status": normalize_text(field_value(entity, fields, "报告状态")),
            "attachments": feishu_sync_service._parse_attachment_field(
                field_value(entity, fields, "附件")
            ),
            "record_id": record_id,
            "feishu_base_table_id": entity.table_id,
            "feishu_base_record_id": record_id,
            "feishu_sync_status": "synced",
            "feishu_last_sync_direction": "base_to_system",
            "feishu_synced_at": modified_at,
            "feishu_source_updated_at": modified_at,
            "created_at": created_at,
            "updated_at": modified_at,
        }

    raise NotFoundException(resource="偏差报告记录")


async def _get_deviation_investigation_push_record_from_feishu(
    db: AsyncSession,
    feishu_record_id: str,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(
        "deviation_investigation_push_record", direction="pull"
    )
    if not runtime.is_enabled() or not entity:
        raise AppException(message="调查推送飞书 Base 未启用")

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_investigation_push_record",
        None,
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    normalize_review_result = feishu_sync_service._normalize_review_result
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    for record in records:
        if str(record.get("record_id") or "") != feishu_record_id:
            continue
        fields = record.get("fields") or {}
        current_deviation_code = (
            normalize_text(field_value(entity, fields, "偏差编号")) or ""
        )
        current_push_round = (
            normalize_text(field_value(entity, fields, "第N次推送")) or "第1次"
        )
        submitted_at_value = parse_datetime(field_value(entity, fields, "提交日期"))
        parsed_item = DeviationInvestigationPushRecordListItem(
            id=record.get("record_id", ""),
            deviation_code=current_deviation_code,
            push_round=current_push_round,
            investigation_report_url=_extract_feishu_link(
                field_value(entity, fields, "偏差调查报告")
            ),
            submitted_at=submitted_at_value,
            submitter=normalize_text(field_value(entity, fields, "提交人")),
            submitters=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "提交人")
            ),
            department_head=normalize_text(field_value(entity, fields, "部门负责人")),
            department_heads=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "部门负责人")
            ),
            department_head_result=normalize_review_result(
                field_value(entity, fields, "部门负责人审核结果")
            ),
            department_head_reviewed_at=parse_datetime(
                field_value(entity, fields, "部门负责人审核时间")
            ),
            qa_name=normalize_text(field_value(entity, fields, "QA")),
            qas=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA")
            ),
            qa_result=normalize_review_result(
                field_value(entity, fields, "QA审核结果")
            ),
            qa_reviewed_at=parse_datetime(field_value(entity, fields, "QA审核时间")),
            qa_head_name=normalize_text(field_value(entity, fields, "QA负责人")),
            qa_heads=feishu_sync_service._parse_person_field(
                field_value(entity, fields, "QA负责人")
            ),
            qa_head_result=normalize_review_result(
                field_value(entity, fields, "QA负责人审核结果")
            ),
            qa_head_reviewed_at=parse_datetime(
                field_value(entity, fields, "QA负责人审核时间")
            ),
            feishu_base_table_id=entity.table_id,
            feishu_base_record_id=record.get("record_id"),
            feishu_sync_status="synced",
            feishu_last_sync_error=None,
            feishu_last_sync_direction="base_to_system",
            feishu_synced_at=get_record_modified_at(record),
            feishu_source_updated_at=get_record_modified_at(record),
            created_at=_get_record_created_at(record) or get_record_modified_at(record),
            updated_at=get_record_modified_at(record),
        ).model_dump()
        return record, parsed_item, feishu_sync_service
    raise NotFoundException(resource="偏差调查推送记录")


async def get_deviation_investigation_push_record_list(
    db: AsyncSession,
    *,
    deviation_id: uuid.UUID | None = None,
    deviation_code: str | None = None,
    push_round: str | None = None,
    submitter: str | None = None,
    department_head_result: str | None = None,
    qa_result: str | None = None,
    qa_head_result: str | None = None,
    submitted_at_from: str | None = None,
    submitted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    return await _build_deviation_investigation_push_items_from_feishu(
        db,
        deviation_id=deviation_id,
        deviation_code=deviation_code,
        push_round=push_round,
        submitter=submitter,
        department_head_result=department_head_result,
        qa_result=qa_result,
        qa_head_result=qa_head_result,
        submitted_at_from=_parse_datetime_filter(submitted_at_from),
        submitted_at_to=_parse_datetime_filter_end_exclusive(submitted_at_to),
        page=page,
        page_size=page_size,
    )


async def get_deviation_investigation_push_record_detail(
    db: AsyncSession, record_id: uuid.UUID
) -> DeviationInvestigationPushRecordDetail:
    record = await repository.get_deviation_investigation_push_record_by_id(
        db, record_id
    )
    if not record:
        raise NotFoundException(resource="偏差调查推送记录", resource_id=str(record_id))
    return DeviationInvestigationPushRecordDetail.model_validate(record)


async def _dump_deviation_investigation_push_record(
    db: AsyncSession, record_id: uuid.UUID
) -> dict[str, Any]:
    record = await repository.get_deviation_investigation_push_record_by_id(
        db, record_id
    )
    if not record:
        raise NotFoundException(resource="偏差调查推送记录", resource_id=str(record_id))
    return DeviationInvestigationPushRecordDetail.model_validate(record).model_dump(
        mode="json"
    )


async def create_deviation_investigation_push_record(
    db: AsyncSession,
    data: CreateDeviationInvestigationPushRecordRequest,
    user_id: str,
) -> dict[str, str]:
    if data.deviation_id is None:
        raise AppException(message="偏差记录不能为空")
    deviation = await repository.get_deviation_by_id(db, data.deviation_id)
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(data.deviation_id))

    submitter_contact = await _resolve_selected_submitter_contact(
        db, data.submitter_open_id
    )
    investigation_report_url = _to_feishu_url_field(data.investigation_report_url)
    if not data.push_round.strip():
        raise AppException(message="第N次推送不能为空")

    payload = data.model_dump()
    payload.pop("submitter_open_id", None)
    payload["deviation_code"] = deviation.deviation_code
    payload["push_round"] = data.push_round.strip()
    payload["investigation_report_url"] = investigation_report_url
    payload["submitted_at"] = data.submitted_at or datetime.now(UTC)
    payload["submitter"] = submitter_contact["name"] or deviation.discoverer or ""
    payload["department_head"] = (
        submitter_contact["department_head_name"]
        or payload.get("department_head")
        or ""
    )
    payload["created_by"] = None
    payload["updated_by"] = None
    record = await repository.create_deviation_investigation_push_record(db, payload)
    await db.commit()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_investigation_push_record_after_write(
        db, record.id
    )
    return await _dump_deviation_investigation_push_record(db, record.id)


async def update_deviation_investigation_push_record(
    db: AsyncSession,
    record_id: str | uuid.UUID,
    data: UpdateDeviationInvestigationPushRecordRequest,
    user_id: str,
) -> dict[str, Any]:
    try:
        local_id = (
            record_id if isinstance(record_id, uuid.UUID) else uuid.UUID(str(record_id))
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Deviation investigation push record {record_id} not found"
        ) from exc

    record = await repository.get_deviation_investigation_push_record_by_id(
        db, local_id
    )
    if not record:
        raise ValueError(f"Deviation investigation push record {record_id} not found")

    payload = data.model_dump(exclude_unset=True)
    await repository.update_deviation_investigation_push_record(db, record, payload)
    await db.commit()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_investigation_push_record_after_write(
        db, record.id
    )
    return await _dump_deviation_investigation_push_record(db, record.id)


async def update_deviation_investigation_push_record_by_ref(
    db: AsyncSession,
    record_ref: str,
    data: UpdateDeviationInvestigationPushRecordRequest,
    user_id: str,
) -> dict[str, Any]:
    if isinstance(record_ref, uuid.UUID):
        local_id = record_ref
    else:
        try:
            local_id = uuid.UUID(str(record_ref))
        except (ValueError, TypeError):
            local_id = None

    if local_id:
        local_record = await repository.get_deviation_investigation_push_record_by_id(
            db, local_id
        )
        if local_record:
            return await update_deviation_investigation_push_record(
                db, local_id, data, user_id
            )

    (
        _,
        remote_item,
        feishu_sync_service,
    ) = await _get_deviation_investigation_push_record_from_feishu(db, record_ref)
    payload = data.model_dump(exclude_unset=True)
    merged = {**remote_item, **payload}
    deviation = await repository.get_deviation_by_code(db, merged["deviation_code"])
    department = deviation.department if deviation else None

    fields = {
        "偏差编号": merged["deviation_code"],
        "第N次推送": merged["push_round"],
        "偏差调查报告": feishu_sync_service._to_feishu_url_field_value(
            merged.get("investigation_report_url")
        ),
        "提交日期": feishu_sync_service._to_ms_timestamp(merged.get("submitted_at")),
        "提交人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            merged.get("submitter"),
            department=department,
        ),
        "部门负责人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db,
            merged.get("department_head"),
            department=department,
        ),
        "部门负责人审核结果": feishu_sync_service._to_feishu_review_option(
            merged.get("department_head_result")
        ),
        "部门负责人审核时间": feishu_sync_service._to_ms_timestamp(
            merged.get("department_head_reviewed_at")
        ),
        "QA": await feishu_sync_service._resolve_contact_bitable_user_value(
            db, merged.get("qa_name")
        ),
        "QA审核结果": feishu_sync_service._to_feishu_review_option(
            merged.get("qa_result")
        ),
        "QA审核时间": feishu_sync_service._to_ms_timestamp(
            merged.get("qa_reviewed_at")
        ),
        "QA负责人": await feishu_sync_service._resolve_contact_bitable_user_value(
            db, merged.get("qa_head_name")
        ),
        "QA负责人审核结果": feishu_sync_service._to_feishu_review_option(
            merged.get("qa_head_result")
        ),
        "QA负责人审核时间": feishu_sync_service._to_ms_timestamp(
            merged.get("qa_head_reviewed_at")
        ),
    }
    try:
        next_record_id, table_id = await feishu_sync_service.feishu_sync._upsert_record(
            db,
            "deviation_investigation_push_record",
            None,
            record_ref,
            fields,
            search_conditions=[
                ("偏差编号", merged["deviation_code"]),
                ("第N次推送", merged["push_round"]),
            ],
        )
    except Exception:
        raise
    merged["id"] = next_record_id
    merged["feishu_base_record_id"] = next_record_id
    merged["feishu_base_table_id"] = table_id
    merged["feishu_sync_status"] = "synced"
    merged["feishu_last_sync_error"] = None
    merged["feishu_last_sync_direction"] = "system_to_base"
    return merged


async def sync_deviation_investigation_push_record_to_feishu_by_ref(
    db: AsyncSession,
    record_ref: str,
) -> dict[str, Any]:
    try:
        local_id = uuid.UUID(record_ref)
    except ValueError:
        local_id = None

    if local_id:
        local_record = await repository.get_deviation_investigation_push_record_by_id(
            db, local_id
        )
        if local_record:
            from app.modules.quality.service import (
                quality_feishu_sync as feishu_sync_service,
            )

            sync_push_record = (
                feishu_sync_service.sync_deviation_investigation_push_record_to_feishu
            )
            return await sync_push_record(
                db,
                local_id,
            )

    _, remote_item, _ = await _get_deviation_investigation_push_record_from_feishu(
        db, record_ref
    )
    return {
        "record_id": remote_item.get("feishu_base_record_id") or record_ref,
        "table_id": remote_item.get("feishu_base_table_id"),
    }


async def get_capa_plan_track_list(
    db: AsyncSession,
    *,
    capa_id: uuid.UUID | None = None,
    capa_code: str | None = None,
    progress: str | None = None,
    owner_name: str | None = None,
    reminder_status: str | None = None,
    due_date_from: str | None = None,
    due_date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    items, total = await repository.get_capa_plan_tracks(
        db,
        capa_id=capa_id,
        capa_code=capa_code,
        progress=progress,
        owner_name=owner_name,
        reminder_status=reminder_status,
        due_date_from=_parse_date_filter(due_date_from),
        due_date_to=_parse_date_filter(due_date_to),
        page=page,
        page_size=page_size,
    )
    return _build_page_result(
        _serialize_capa_plan_track_items(items),
        total,
        page,
        page_size,
    )


async def get_capa_plan_track_detail(
    db: AsyncSession, track_id: uuid.UUID
) -> CapaPlanTrackDetail:
    track = await repository.get_capa_plan_track_by_id(db, track_id)
    if not track:
        raise NotFoundException(resource="CAPA计划跟踪", resource_id=str(track_id))
    return _cap_plan_track_to_detail(track)


def _cap_plan_track_to_detail(track: Any) -> CapaPlanTrackDetail:
    """Convert ORM object to detail schema, bypassing SQLAlchemy descriptor protocol."""
    raw = {k: v for k, v in track.__dict__.items() if not k.startswith("_sa_")}
    for col in track.__table__.columns:
        if col.key not in raw:
            raw[col.key] = None
    # Fix None values for required datetime columns
    now = datetime.now(UTC)
    for key in ("created_at", "updated_at"):
        if raw.get(key) is None:
            raw[key] = now
    return CapaPlanTrackDetail(**raw)


def _cap_plan_track_to_dict(track: Any) -> dict[str, Any]:
    """Convert ORM object to plain dict, bypassing all Pydantic validation."""
    return _cap_plan_track_to_detail(track).model_dump(mode="json")


async def create_capa_plan_track(
    db: AsyncSession,
    data: CreateCapaPlanTrackRequest,
    user_id: str,
) -> dict[str, str]:
    capa = await repository.get_capa_by_id(db, data.capa_id)
    if not capa:
        raise NotFoundException(resource="CAPA", resource_id=str(data.capa_id))

    payload = data.model_dump()
    payload["capa_code"] = capa.capa_code
    payload["created_by"] = None
    payload["updated_by"] = None
    record = await repository.create_capa_plan_track(db, payload)
    await db.commit()
    # Re-fetch to ensure all server-generated columns are loaded
    result = await repository.get_capa_plan_track_by_id(db, record.id)
    if not result:
        raise AppException(message=f"Failed to re-fetch CAPA plan track {record.id}")
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_plan_track_after_write(db, record.id)
    return _cap_plan_track_to_dict(result)


async def update_capa_plan_track(
    db: AsyncSession,
    track_id: uuid.UUID,
    data: UpdateCapaPlanTrackRequest,
    user_id: str,
) -> dict[str, str]:
    track = await repository.get_capa_plan_track_by_id(db, track_id)
    if not track:
        raise NotFoundException(resource="CAPA计划跟踪", resource_id=str(track_id))

    payload = data.model_dump(exclude_unset=True)
    await repository.update_capa_plan_track(db, track, payload)
    await db.commit()
    result = await repository.get_capa_plan_track_by_id(db, track.id)
    if not result:
        raise AppException(message=f"Failed to re-fetch CAPA plan track {track.id}")
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_plan_track_after_write(db, track.id)
    return _cap_plan_track_to_detail(result).model_dump(mode="json")


async def delete_capa_plan_track(
    db: AsyncSession,
    track_id: uuid.UUID,
) -> None:
    await repository.delete_capa_plan_track(db, track_id)
    await db.commit()


def _normalize_checkbox_result(value: Any) -> str:
    return "已确认" if value else "待确认"


async def get_deviation_report_record_list_from_feishu(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("deviation_report_record", direction="pull")
    if not runtime.is_enabled() or not entity:
        return _build_page_result([], 0, page, page_size)

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_report_record",
        None,
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    items: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        modified_at = get_record_modified_at(record)
        created_at = parse_datetime(record.get("created_time")) or modified_at
        record_id = str(record.get("record_id") or "")
        items.append(
            {
                "deviation_code": normalize_text(
                    field_value(entity, fields, "偏差编号")
                ),
                "description": normalize_text(field_value(entity, fields, "偏差内容")),
                "report_time": parse_datetime(field_value(entity, fields, "报告时间")),
                "product_batch": normalize_text(
                    field_value(entity, fields, "涉及产品名称/批号")
                ),
                "department": normalize_text(field_value(entity, fields, "部门")),
                "reporter_name": normalize_text(field_value(entity, fields, "报告人")),
                "reporters": feishu_sync_service._parse_person_field(
                    field_value(entity, fields, "报告人")
                ),
                "department_head": normalize_text(
                    field_value(entity, fields, "部门负责人")
                ),
                "department_heads": feishu_sync_service._parse_person_field(
                    field_value(entity, fields, "部门负责人")
                ),
                "department_head_result": _normalize_checkbox_result(
                    field_value(entity, fields, "部门负责人确认")
                ),
                "department_head_reviewed_at": parse_datetime(
                    field_value(entity, fields, "部门负责人确认时间")
                ),
                "qa_name": normalize_text(field_value(entity, fields, "QA")),
                "qas": feishu_sync_service._parse_person_field(
                    field_value(entity, fields, "QA")
                ),
                "qa_result": _normalize_checkbox_result(
                    field_value(entity, fields, "QA确认")
                ),
                "qa_reviewed_at": parse_datetime(
                    field_value(entity, fields, "QA确认时间")
                ),
                "qa_head_name": normalize_text(field_value(entity, fields, "QA负责人")),
                "qa_heads": feishu_sync_service._parse_person_field(
                    field_value(entity, fields, "QA负责人")
                ),
                "qa_head_result": _normalize_checkbox_result(
                    field_value(entity, fields, "QA负责人确认")
                ),
                "qa_head_reviewed_at": parse_datetime(
                    field_value(entity, fields, "QA负责人确认时间")
                ),
                "report_status": normalize_text(
                    field_value(entity, fields, "报告状态")
                ),
                "attachments": feishu_sync_service._parse_attachment_field(
                    field_value(entity, fields, "附件")
                ),
                "record_id": record_id,
                "feishu_base_table_id": entity.table_id,
                "feishu_base_record_id": record_id,
                "feishu_sync_status": "synced",
                "feishu_last_sync_direction": "base_to_system",
                "feishu_synced_at": modified_at,
                "feishu_source_updated_at": modified_at,
                "created_at": created_at,
                "updated_at": modified_at,
            }
        )

    items.sort(
        key=lambda item: (
            item.get("report_time") or datetime.min.replace(tzinfo=UTC),
            item.get("feishu_source_updated_at") or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)
