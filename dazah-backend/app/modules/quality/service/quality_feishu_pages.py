from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.core.redis import cache_delete, cache_get, cache_set
from app.modules.quality import repository
from app.modules.quality.models import CAPA, CapaPlanTrack, ChangeControl
from app.modules.quality.service import (
    quality_feishu_settings as feishu_settings_service,
)
from app.modules.quality.service import (
    quality_feishu_sync as feishu_sync_service,
)
from app.modules.quality.service import (
    quality_management as quality_management_service,
)
from app.modules.quality.service import (
    tracking_records as tracking_service,
)
from app.modules.quality.service import (
    validation_classification as validation_classification_service,
)
from app.platform.audit.service import record_audit_log
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)


def _contains_text(value: Any, keyword: str | None) -> bool:
    """Compatibility export used by the split Feishu page services."""
    return tracking_service._contains_text(value, keyword)


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


def _parse_datetime_like(value: Any) -> datetime | None:
    return feishu_sync_service._parse_feishu_datetime(value)


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
) -> tuple[
    feishu_sync_service.QualityFeishuRuntimeConfig,
    feishu_sync_service.QualityFeishuEntityRuntimeConfig,
]:
    # 确保实体配置存在（自动创建缺失的配置，防止数据丢失）
    await feishu_settings_service.ensure_quality_feishu_entity_settings(db)
    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config(entity_code, direction=direction)
    if (
        not runtime.is_enabled()
        or not entity
        or not entity.app_token
        or not entity.table_id
    ):
        raise AppException(message=f"{entity_code} 飞书 Base 未启用")
    return runtime, entity


async def _search_entity_records(
    db: AsyncSession,
    entity_code: str,
    *,
    filters: dict[str, Any] | None = None,
    field_names: list[str] | None = None,
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
        field_names=field_names,
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
    actor_user_id: uuid.UUID | None = None,
) -> None:
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    # GMP 删除留痕：飞书记录为物理删除，删除前必须先落审计
    await record_audit_log(
        db,
        action="feishu_record_deleted",
        user_id=actor_user_id,
        resource_type=f"quality.feishu.{entity_code}",
        extra={
            "feishu_record_id": record_id,
            "feishu_table_id": entity.table_id,
        },
    )
    await db.commit()
    if not entity.table_id:
        raise AppException(message="飞书表未配置", status_code=503)
    await client.delete_record(entity.table_id, record_id)


def _normalize_closed_status(value: Any) -> str:
    normalized = feishu_sync_service._normalize_bool_from_yes_no(value)
    return "closed" if normalized else "draft"


def _normalize_yes_no(value: bool | None) -> str:
    if value is None:
        return ""
    return "是" if value else "否"


def _split_related_capa_codes(value: Any) -> list[str] | None:
    normalized = feishu_sync_service._normalize_text(value)
    if not normalized:
        return None
    codes = [code.strip() for code in re.split(r"[,，/、\s]+", normalized)]
    return [code for code in codes if code] or None


def _map_deviation_ledger_base_item(
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
        "id": str(record.get("record_id") or ""),
        "record_id": str(record.get("record_id") or ""),
        "deviation_code": normalize_text(field_value(entity, fields, "偏差编号")) or "",
        "final_code": None,
        "title": normalize_text(field_value(entity, fields, "偏差简要描述")) or "",
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
        "description": normalize_text(field_value(entity, fields, "偏差简要描述")),
        "has_occurred_before": feishu_sync_service._normalize_bool_from_yes_no(
            field_value(entity, fields, "偏差是否曾发生")
        ),
        "material_disposition": normalize_text(
            field_value(entity, fields, "产品/物料处理结果")
        ),
        "corrective_actions": normalize_text(
            field_value(entity, fields, "纠正预防措施")
        ),
        "root_cause_analysis": normalize_text(field_value(entity, fields, "根本原因")),
        "investigation_completed_at": parse_datetime(
            field_value(entity, fields, "调查完成时间")
        ),
        "close_time": parse_datetime(field_value(entity, fields, "关闭时间")),
        "related_capa_codes": _split_related_capa_codes(
            field_value(entity, fields, "关联capa")
        ),
        "related_capas": None,
        "feishu_base_table_id": entity.table_id,
        "feishu_base_record_id": str(record.get("record_id") or ""),
        "feishu_sync_status": "synced",
        "feishu_last_sync_error": None,
        "feishu_last_sync_direction": "base_to_system",
        "feishu_synced_at": modified_at,
        "feishu_source_updated_at": modified_at,
        "status_updated_at": parse_datetime(field_value(entity, fields, "关闭时间")),
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
    affected_items = str(payload.get("affected_items") or "").strip()
    batch_number = str(payload.get("batch_number") or "").strip()
    product_batch = str(payload.get("product_batch") or "").strip()
    combined_product_batch = product_batch or feishu_sync_service._join_non_empty(
        [affected_items or None, batch_number or None]
    )
    is_closed = payload.get("is_closed")
    if is_closed is None and payload.get("status") is not None:
        is_closed = str(payload.get("status")).strip().lower() == "closed"
    return {
        "偏差编号": deviation_code,
        "产品名称/批号": combined_product_batch or "",
        "偏差简要描述": str(
            payload.get("description") or payload.get("title") or ""
        ).strip(),
        "偏差是否曾发生": "是"
        if payload.get("has_occurred_before") is True
        else "否"
        if payload.get("has_occurred_before") is False
        else "",
        "根本原因": str(payload.get("root_cause_analysis") or "").strip(),
        "偏差等级": str(payload.get("level") or "").strip(),
        "调查完成时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("investigation_completed_at"))
        ),
        "纠正预防措施": str(payload.get("corrective_actions") or "").strip(),
        "产品/物料处理结果": str(payload.get("material_disposition") or "").strip(),
        "是否关闭": "是" if is_closed is True else "否" if is_closed is False else "",
        "关闭时间": feishu_sync_service._to_ms_timestamp(
            _parse_datetime_like(payload.get("close_time"))
        ),
        "关联capa": "、".join(payload.get("related_capa_codes") or []),
    }


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
    selected_ids = {value.strip() for value in (record_ids or []) if value.strip()}
    filtered = []
    for item in items:
        if selected_ids and item["record_id"] not in selected_ids:
            continue
        searchable = " ".join(
            str(item.get(key) or "")
            for key in ("deviation_code", "title", "description")
        )
        if keyword and keyword.lower() not in searchable.lower():
            continue
        if (
            deviation_code
            and deviation_code.lower()
            not in str(item.get("deviation_code") or "").lower()
        ):
            continue
        if (
            product_keyword
            and product_keyword.lower()
            not in str(item.get("affected_items") or "").lower()
        ):
            continue
        if (
            has_occurred_before is not None
            and item.get("has_occurred_before") != has_occurred_before
        ):
            continue
        if is_closed is not None and (item.get("status") == "closed") != is_closed:
            continue
        if (
            root_cause_keyword
            and root_cause_keyword.lower()
            not in str(item.get("root_cause_analysis") or "").lower()
        ):
            continue
        if (
            corrective_actions_keyword
            and corrective_actions_keyword.lower()
            not in str(item.get("corrective_actions") or "").lower()
        ):
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda item: str(
            item.get("feishu_source_updated_at") or item.get("created_at") or ""
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    return _build_page_result(
        filtered[start : start + page_size], len(filtered), page, page_size
    )


async def get_deviation_ledger_record(
    db: AsyncSession, record_id: str
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(db, "deviation_ledger", direction="pull")
    for record in await _search_entity_records(db, "deviation_ledger"):
        if str(record.get("record_id") or "") == record_id:
            return _map_deviation_ledger_detail_item(record, entity)
    raise NotFoundException(resource="飞书偏差台账记录", resource_id=record_id)


async def create_deviation_ledger_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    deviation_code = str(payload.get("deviation_code") or "").strip()
    if not deviation_code:
        deviation_code = (
            await quality_management_service._generate_monthly_deviation_code(
                db, datetime.now(UTC)
            )
        )
    created = await _create_entity_record(
        db,
        "deviation_ledger",
        _build_deviation_ledger_fields(payload, deviation_code=deviation_code),
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
        raise AppException(message="飞书偏差台账记录缺少偏差编号")
    await _update_entity_record(
        db,
        "deviation_ledger",
        record_id,
        _build_deviation_ledger_fields(merged, deviation_code=deviation_code),
        search_conditions=[("偏差编号", deviation_code)],
    )
    return await get_deviation_ledger_record(db, record_id)


async def delete_deviation_ledger_record(db: AsyncSession, record_id: str) -> None:
    await _delete_entity_record(db, "deviation_ledger", record_id)


async def _get_investigation_push_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    (
        _,
        item,
        _,
    ) = await tracking_service._get_deviation_investigation_push_record_from_feishu(
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


async def get_deviation_report_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    """获取单条偏差报告记录。"""
    item = await tracking_service.get_deviation_report_record_from_feishu(db, record_id)
    return _serialize_report_record_alias(item)


async def create_deviation_report_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """创建偏差报告记录到飞书多维表格。

    只需填写偏差内容、涉及产品名称/批号、报告人。
    偏差编号自动生成（PC-YYMM###），报告时间为提交时间，
    部门根据报告人从部门联系人中自动填充。
    """
    description = str(payload.get("description") or "").strip()
    product_batch = str(payload.get("product_batch") or "").strip()
    reporter_open_id = str(payload.get("reporter_open_id") or "").strip()

    if not description:
        raise AppException(message="偏差内容不能为空")
    if not product_batch:
        raise AppException(message="涉及产品名称/批号不能为空")
    if not reporter_open_id:
        raise AppException(message="报告人不能为空")

    # 从部门联系人中解析报告人信息（包含 name, department）
    reporter_contact = (
        await quality_management_service._resolve_selected_reporter_contact(
            db, reporter_open_id
        )
    )
    department = (reporter_contact.department or "").strip()
    if not department:
        raise AppException(message="报告人未关联部门，请先在部门联系人中设置")

    # 生成偏差编号 PC-YYMM###
    now = datetime.now(UTC)
    deviation_code = await quality_management_service._generate_monthly_deviation_code(
        db, now
    )

    # 解析报告人的飞书用户ID
    reporter_user_value = await feishu_sync_service._resolve_contact_bitable_user_value(
        db, reporter_contact.name, department=department
    )

    # 构建飞书字段
    fields: dict[str, Any] = {
        "偏差编号": deviation_code,
        "报告时间": feishu_sync_service._to_ms_timestamp(now),
        "偏差内容": description,
        "涉及产品名称/批号": product_batch,
        "部门": department,
        "报告状态": "待确认",
    }
    if reporter_user_value:
        fields["报告人"] = reporter_user_value

    # 创建飞书记录
    created = await _create_entity_record(
        db,
        "deviation_report_record",
        fields,
        search_conditions=[("偏差编号", deviation_code)],
    )

    return await get_deviation_report_record(db, created["record_id"])


async def _build_report_record_fields(
    db: AsyncSession,
    payload: dict[str, Any],
    *,
    deviation_code: str,
) -> dict[str, Any]:
    """构建偏差报告记录的飞书可编辑字段（偏差内容、涉及产品名称/批号、报告人、附件）。

    只写入用户可编辑字段，不覆盖确认流程字段（部门负责人、QA、报告状态等）。
    """
    description = str(payload.get("description") or "").strip()
    product_batch = str(payload.get("product_batch") or "").strip()
    reporter_open_id = str(payload.get("reporter_open_id") or "").strip()
    reporter_name = str(payload.get("reporter_name") or "").strip()

    fields: dict[str, Any] = {
        "偏差编号": deviation_code,
        "偏差内容": description,
        "涉及产品名称/批号": product_batch,
    }

    department = str(payload.get("department") or "").strip() or None
    reporter_user_value = None
    if reporter_open_id:
        reporter_contact = (
            await quality_management_service._resolve_selected_reporter_contact(
                db, reporter_open_id
            )
        )
        department = (reporter_contact.department or "").strip() or department
        reporter_user_value = (
            await feishu_sync_service._resolve_contact_bitable_user_value(
                db, reporter_contact.name, department=department
            )
        )
    elif reporter_name:
        reporter_user_value = (
            await feishu_sync_service._resolve_contact_bitable_user_value(
                db, reporter_name, department=department
            )
        )
    if department:
        fields["部门"] = department
    if reporter_user_value:
        fields["报告人"] = reporter_user_value

    if payload.get("attachments") is not None:
        fields["附件"] = payload["attachments"]

    return fields


async def update_deviation_report_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """更新偏差报告记录到飞书多维表格（仅用户可编辑字段）。"""
    current = await get_deviation_report_record(db, record_id)
    merged = {**current, **payload}
    deviation_code = str(merged.get("deviation_code") or "").strip()
    if not deviation_code:
        raise AppException(message="飞书偏差报告记录缺少偏差编号")
    fields = await _build_report_record_fields(
        db, merged, deviation_code=deviation_code
    )
    await _update_entity_record(
        db,
        "deviation_report_record",
        record_id,
        fields,
        search_conditions=[("偏差编号", deviation_code)],
    )
    return await get_deviation_report_record(db, record_id)


async def delete_deviation_report_record(
    db: AsyncSession,
    record_id: str,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    # 删除前校验记录存在，避免对不存在的飞书记录抛 500
    await get_deviation_report_record(db, record_id)
    await _delete_entity_record(
        db, "deviation_report_record", record_id, actor_user_id=actor_user_id
    )


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
        deviation_id=uuid.UUID(deviation_id) if deviation_id else None,
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
            raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
        deviation_code = deviation.deviation_code
    if not deviation_code:
        raise AppException(message="偏差编号不能为空")

    push_round = str(payload.get("push_round") or "").strip()
    if not push_round:
        raise AppException(message="第N次推送不能为空")

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
    actor_user_id: uuid.UUID | None = None,
) -> None:
    await _get_investigation_push_record(db, record_id)
    await _delete_entity_record(
        db, "deviation_investigation_push_record", record_id, actor_user_id
    )


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
    except AppException:
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
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    """Delete the Feishu change_ledger record matching the given change_code.

    Returns True if a record was found and deleted, False otherwise.
    """
    record_id = await _find_change_feishu_record_id(db, change_code)
    if not record_id:
        return False
    if actor_user_id is None:
        await _delete_entity_record(db, "change_ledger", record_id)
    else:
        await _delete_entity_record(db, "change_ledger", record_id, actor_user_id)
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
        _, _entity = await _resolve_runtime_entity(
            db, "change_ledger", direction="pull"
        )
    except AppException:
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
                    ChangeControl.is_deleted.is_(False),
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.serial_number = serial_number
                existing.applicant_department = applicant_department
                existing.change_object = change_object
                existing.change_content = change_content
                existing.change_level = change_level
                existing.application_date = (
                    application_date.date() if application_date else None
                )
                existing.planned_approval_date = (
                    planned_approval_date.date() if planned_approval_date else None
                )
                existing.execution_date = (
                    execution_date.date() if execution_date else None
                )
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
                    application_date=application_date.date()
                    if application_date
                    else None,
                    planned_approval_date=planned_approval_date.date()
                    if planned_approval_date
                    else None,
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
                logger.warning("rollback 失败", exc_info=True)
            logger.exception("同步变更台账记录失败: %s", record.get("record_id"))
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
    "其他验证": "other_validation",
}

# 英文代码 -> 飞书验证类别中文
VALIDATION_TYPE_CODE_TO_FEISHU: dict[str, str] = {
    "equipment_qualification": "设备确认",
    "process_validation": "工艺验证",
    "cleaning_validation": "清洁验证",
    "other_validation": "其他验证",
}


def _entity_code_for_validation_type(
    validation_type: str | None,
    year: int | None = None,
) -> str:
    base = (
        VALIDATION_TYPE_ENTITY_MAP.get(validation_type, "validation_master_plan")
        if validation_type
        else "validation_master_plan"
    )
    if year:
        return f"{base}_{year}"
    return base


async def _invalidate_validation_list_cache(entity_code: str) -> None:
    """清除指定实体的验证列表缓存（写操作后调用，保证列表即时刷新）。"""
    try:
        from app.core.redis import redis_client

        async for key in redis_client.scan_iter(
            f"quality:validation:list:{entity_code}:*"
        ):
            await cache_delete(key)
    except Exception:
        logger.warning("验证列表缓存清理失败（忽略）", exc_info=True)


_DEPARTMENT_CONTACTS_CACHE_KEY = "quality:department_contacts:list"
_DEPARTMENT_CONTACTS_CACHE_TTL = 300


async def _get_department_contacts_cache(db: AsyncSession) -> list[dict[str, Any]]:
    """获取部门联系人（Redis 缓存 5 分钟，避免每个列表请求都拉飞书）"""
    cached = await cache_get(_DEPARTMENT_CONTACTS_CACHE_KEY)
    if cached is not None:
        try:
            parsed = json.loads(cached)
            if isinstance(parsed, list):
                return parsed
        except (TypeError, ValueError):
            pass
    try:
        from app.modules.quality.service.department_contacts import (
            get_department_contact_list_from_feishu,
        )

        result = await get_department_contact_list_from_feishu(
            db, page=1, page_size=1000
        )
        items = result.get("items", [])
        items = items if isinstance(items, list) else []
        await cache_set(
            _DEPARTMENT_CONTACTS_CACHE_KEY,
            json.dumps(items, ensure_ascii=False, default=str),
            ex=_DEPARTMENT_CONTACTS_CACHE_TTL,
        )
        return items
    except Exception:
        # 部门联系人未配置/拉取失败时头像为空，不影响验证列表加载
        logger.warning("拉取部门联系人失败，人员头像跳过", exc_info=True)
        return []


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
    month_match = re.fullmatch(r"(\d{4})(?:[.\-/年]?)(\d{1,2})(?:月)?", text)
    if month_match:
        try:
            return date(int(month_match.group(1)), int(month_match.group(2)), 1)
        except ValueError:
            return None
    try:
        parsed = _parse_datetime_like(text)
    except (TypeError, ValueError):
        return None
    return parsed.date() if parsed else None


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
        product_codes = [
            str(item).strip() for item in product_codes_raw if str(item).strip()
        ]
    elif isinstance(product_codes_raw, str) and product_codes_raw.strip():
        product_codes = [product_codes_raw.strip()]

    feishu_val_type_raw = fields.get("验证类别")
    parsed_val_type = _parse_feishu_text_field(feishu_val_type_raw) or ""
    if parsed_val_type:
        validation_type = _translate_validation_type_f2c(parsed_val_type)
        validation_type_source = "feishu"
    else:
        # 真实年度台账没有"验证类别"列（或值为空）→ 标记待 AI 按名称分类
        validation_type = "other_validation"
        validation_type_source = "inferred"

    drafted_date = parse_date(fields.get("起草时间"))
    approved_date = parse_date(fields.get("批准时间"))
    # 验证总表用 报告起草时间/报告批准时间，真实年度台账用 起草时间1/批准时间1
    drafted_date_1 = parse_date(fields.get("报告起草时间")) or parse_date(
        fields.get("起草时间1")
    )
    approved_date_1 = parse_date(fields.get("报告批准时间")) or parse_date(
        fields.get("批准时间1")
    )
    # 验证到期时间是文本字段（如 "2026.02"），不是日期
    planned_end_text = _parse_feishu_text_field(fields.get("验证到期时间"))

    revalidation_years_raw = _parse_feishu_text_field(fields.get("再验证周期（几年）"))
    revalidation_years: int | None = None
    if revalidation_years_raw:
        digits = "".join(c for c in revalidation_years_raw if c.isdigit())
        if digits:
            revalidation_years = int(digits)

    # 人员字段是用户类型：保留 name/avatar_url/id 结构，前端可渲染头像+姓名
    participants_raw = fields.get("人员")
    participants: list[dict[str, str]] | str | None = None
    if isinstance(participants_raw, list):
        persons = []
        for item in participants_raw:
            if isinstance(item, dict):
                if item.get("name"):
                    persons.append(
                        {
                            "name": str(item.get("name") or ""),
                            "avatar_url": str(item.get("avatar_url") or ""),
                            "id": str(item.get("id") or item.get("open_id") or ""),
                        }
                    )
                elif item.get("text"):
                    persons.append(
                        {
                            "name": str(item.get("text") or ""),
                            "avatar_url": "",
                            "id": "",
                        }
                    )
            elif isinstance(item, str) and item.strip():
                persons.append({"name": item.strip(), "avatar_url": "", "id": ""})
        participants = persons if persons else None
    elif participants_raw:
        participants = normalize_text(participants_raw)

    # 负责人字段：同样保留结构化头像信息
    owner_raw = fields.get("负责人")
    owner_name: list[dict[str, str]] | str | None = None
    if isinstance(owner_raw, list):
        owner_persons = []
        for item in owner_raw:
            if isinstance(item, dict):
                if item.get("name"):
                    owner_persons.append(
                        {
                            "name": str(item.get("name") or ""),
                            "avatar_url": str(item.get("avatar_url") or ""),
                            "id": str(item.get("id") or item.get("open_id") or ""),
                        }
                    )
                elif item.get("text"):
                    owner_persons.append(
                        {
                            "name": str(item.get("text") or ""),
                            "avatar_url": "",
                            "id": "",
                        }
                    )
            elif isinstance(item, str) and item.strip():
                owner_persons.append(
                    {
                        "name": item.strip(),
                        "avatar_url": "",
                        "id": "",
                    }
                )
        owner_name = owner_persons if owner_persons else None
    elif owner_raw:
        owner_name = normalize_text(owner_raw)

    # 群组字段是 GroupChat 类型，保留 {id, name, avatar_url} 结构供前端显示群名
    group_chat_raw = fields.get("群组")
    group_chat: list[dict[str, str]] | str | None = None
    if isinstance(group_chat_raw, list):
        groups = []
        for item in group_chat_raw:
            if isinstance(item, dict) and item.get("name"):
                groups.append(
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "avatar_url": str(item.get("avatar_url") or ""),
                    }
                )
        group_chat = groups if groups else None
    elif group_chat_raw:
        group_chat = normalize_text(group_chat_raw)

    return {
        "record_id": str(record.get("record_id") or ""),
        "table_id": None,
        "validation_type": validation_type,
        "validation_type_source": validation_type_source,
        "record_code": "",  # 飞书表中无此字段
        "title": _parse_feishu_text_field(fields.get("确认名称")) or "",
        "status": normalize_text(fields.get("任务状态")),
        "department": normalize_text(fields.get("部门名称")),
        "equipment_code": _parse_feishu_text_field(fields.get("设备编码")),
        "product_codes": product_codes,
        "planned_end_date": planned_end_text,  # 文本格式如 "2026.02"
        "group_chat": group_chat,
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
        # 仅部门（或全空）的占位行：除部门外无任何业务信息 → 前端自动隐藏
        "is_empty_row": not bool(
            _parse_feishu_text_field(fields.get("确认名称"))
            or _parse_feishu_text_field(fields.get("设备编码"))
            or _parse_feishu_text_field(fields.get("方案名称"))
            or _parse_feishu_text_field(fields.get("方案编码"))
            or _parse_feishu_text_field(fields.get("报告编号"))
            or fields.get("人员")
            or fields.get("负责人")
            or fields.get("任务状态")
            or fields.get("验证到期时间")
            or drafted_date
            or approved_date
            or drafted_date_1
            or approved_date_1
            or revalidation_years
        ),
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
    if participants:
        # 支持数组（前端多选）或字符串
        if isinstance(participants, list):
            names_str = "、".join(str(p) for p in participants if p)
        else:
            names_str = str(participants).strip()
        if names_str:
            participant_ids = _resolve_bitable_user_ids_from_names(contacts, names_str)
            if participant_ids:
                fields["人员"] = [{"id": oid} for oid in participant_ids]

    owner = payload.get("owner_name")
    if owner:
        owner_str = (
            str(owner).strip()
            if not isinstance(owner, list)
            else "、".join(str(o) for o in owner if o)
        )
        if owner_str:
            owner_ids = _resolve_bitable_user_ids_from_names(contacts, owner_str)
            if owner_ids:
                fields["负责人"] = [{"id": oid} for oid in owner_ids[:1]]

    # 群组 — GroupChat 类型，不可通过 API 直接写入，跳过
    # gc = payload.get("group_chat")
    # if gc:
    #     fields["群组"] = str(gc).strip()

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


async def _apply_ai_validation_categories(
    db: AsyncSession,
    items: list[dict[str, Any]],
) -> None:
    """对缺少"验证类别"列的记录按确认名称做 AI 分类（带 DB 缓存）。

    顺带用部门联系人补全人员/负责人的头像（飞书用户字段本身不含头像）。
    """
    inferred_titles = sorted(
        {
            str(item.get("title") or "").strip()
            for item in items
            if item.get("validation_type_source") == "inferred"
            and str(item.get("title") or "").strip()
        }
    )
    if inferred_titles:
        try:
            resolve = validation_classification_service.resolve_validation_categories
            categories = await resolve(db, inferred_titles)
        except Exception:
            logger.exception("验证名称 AI 分类失败，保持其他验证归类")
            categories = {}
        for item in items:
            if item.get("validation_type_source") != "inferred":
                continue
            category = categories.get(str(item.get("title") or "").strip())
            if category in validation_classification_service.VALIDATION_CATEGORY_CODES:
                item["validation_type"] = category
            item.pop("validation_type_source", None)
    await _enrich_participants_avatars(db, items)


async def _enrich_participants_avatars(
    db: AsyncSession,
    items: list[dict[str, Any]],
) -> None:
    """用 HR 飞书人员缓存（hr_feishu_members）按姓名补全人员/负责人头像。

    飞书 user 字段本身不含 avatar_url；HR 模块已把飞书通讯录（含头像）
    缓存到本地表，按姓名匹配即可取到头像，不依赖部门联系人表配置。
    """
    try:
        from sqlalchemy import select as _select

        from app.modules.hr.models import HrFeishuMember

        rows = (
            await db.execute(_select(HrFeishuMember))
        ).scalars().all()
    except Exception:
        logger.warning("读取 HR 飞书人员缓存失败，人员头像跳过", exc_info=True)
        return
    avatar_by_name: dict[str, str] = {}
    for member in rows:
        name = str(member.name or "").strip()
        avatar = str(member.avatar_url or "").strip()
        if name and avatar and name not in avatar_by_name:
            avatar_by_name[name] = avatar

    def _fill(person_list: Any) -> None:
        if not isinstance(person_list, list):
            return
        for person in person_list:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not person.get("avatar_url") and name in avatar_by_name:
                person["avatar_url"] = avatar_by_name[name]

    for item in items:
        _fill(item.get("participants"))
        _fill(item.get("owner_name"))


async def _search_validation_records_safe(
    db: AsyncSession,
    entity_code: str,
) -> list[dict[str, Any]]:
    """搜索验证记录；全字段搜索被高级权限受限字段拒绝时按白名单字段重试。

    真实年度台账可能含"无权限访问字段"等应用不可读的特殊列，飞书对
    含受限字段的全字段搜索会整体拒绝，此时排除受限字段后重试。
    """
    try:
        return await _search_entity_records(db, entity_code)
    except Exception:
        pass
    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
        runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
        from app.platform.integrations.feishu.bitable import BitableClient

        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        safe_names = [
            str(item.get("field_name") or "")
            for item in await client.list_fields(entity.table_id)
            if item.get("field_name")
            and not str(item.get("field_name")).startswith("无权限")
        ]
        if not safe_names:
            return []
        return await _search_entity_records(db, entity_code, field_names=safe_names)
    except Exception:
        return []


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
    year: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """从飞书拉取验证记录列表。year 指定时严格读取对应年度表（未配置则为空）。

    结果带 60 秒短时缓存（Redis），降低重复打开/翻页的飞书全量拉取开销；
    写操作（增删改/批量删）会清除对应实体的缓存。
    """
    entity_code = _entity_code_for_validation_type(validation_type, year)
    cache_key = (
        f"quality:validation:list:{entity_code}:{validation_type or ''}:"
        f"{status or ''}:{department or ''}:{keyword or ''}:{page}:{page_size}"
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        try:
            return json.loads(cached)
        except (TypeError, ValueError):
            pass

    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except AppException:
        return _build_page_result([], 0, page, page_size)

    records = await _search_validation_records_safe(db, entity_code)

    items = [_map_validation_base_item(record) for record in records]
    # 隐藏仅部门（无其他业务信息）的占位行
    items = [item for item in items if not item.get("is_empty_row")]
    await _apply_ai_validation_categories(db, items)

    # Filter by validation_type if specified (for child pages)
    if validation_type:
        vtype_to_match = validation_type
        items = [
            item for item in items if item.get("validation_type") == vtype_to_match
        ]

    # Additional filters
    if status:
        items = [item for item in items if item.get("status") == status]
    if department:
        items = [item for item in items if item.get("department") == department]
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

    def _parse_filter_date(value: str | None) -> date | None:
        if not value:
            return None
        return date.fromisoformat(value)

    planned_from = _parse_filter_date(planned_end_date_from)
    planned_to = _parse_filter_date(planned_end_date_to)
    drafted_from = _parse_filter_date(drafted_at_from)
    drafted_to = _parse_filter_date(drafted_at_to)

    def _planned_end_date(item: dict[str, Any]) -> date | None:
        raw = str(item.get("planned_end_date") or "").strip().replace(".", "-")
        if len(raw) == 7:
            raw = f"{raw}-01"
        try:
            return date.fromisoformat(raw) if raw else None
        except ValueError:
            return None

    if planned_from:
        items = [
            item
            for item in items
            if (_planned_end_date(item) or date.min) >= planned_from
        ]
    if planned_to:
        items = [
            item
            for item in items
            if (_planned_end_date(item) or date.max) <= planned_to
        ]
    if drafted_from:
        items = [
            item
            for item in items
            if (item.get("drafted_at") or date.min) >= drafted_from
        ]
    if drafted_to:
        items = [
            item for item in items if (item.get("drafted_at") or date.max) <= drafted_to
        ]

    items.sort(
        key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    result = _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )
    await cache_set(
        cache_key,
        json.dumps(result, ensure_ascii=False, default=str),
        ex=60,
    )
    return result


async def get_validation_record_from_feishu(
    db: AsyncSession,
    record_id: str,
    validation_type: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """从飞书获取单条验证记录详情。"""
    entity_code = _entity_code_for_validation_type(validation_type, year)

    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except AppException:
        if year:
            raise AppException(
                message=(
                    f"{year} 年度验证飞书表未配置，"
                    "请先在质量管理-飞书同步设置中绑定"
                )
            )
        raise AppException(message="验证与确认飞书 Base 未启用")

    records = await _search_validation_records_safe(db, entity_code)
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            item = _map_validation_base_item(record)
            await _apply_ai_validation_categories(db, [item])
            return item
    raise NotFoundException(resource="飞书验证记录")


# 报告日期字段别名：验证总表 vs 真实年度台账字段名不同
_VALIDATION_FIELD_ALIASES: dict[str, str] = {
    "报告起草时间": "起草时间1",
    "报告批准时间": "批准时间1",
}


async def _adapt_validation_fields_to_remote(
    db: AsyncSession,
    entity_code: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """按远端表结构适配写入字段。

    - 报告日期字段别名：验证总表与真实年度台账列名不同（起草时间1/批准时间1）
    - 远端不存在的字段直接丢弃（如年度台账没有"验证类别"列），避免整次写入被飞书拒绝
    - 单选字段收到列表值时取第一项
    """
    try:
        _, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
        runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
        from app.platform.integrations.feishu.bitable import BitableClient

        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        remote_map: dict[str, dict[str, Any]] = {
            str(item.get("field_name") or ""): item
            for item in await client.list_fields(entity.table_id)
            if item.get("field_name")
        }
    except Exception:
        return fields
    adapted = dict(fields)
    for src, dst in _VALIDATION_FIELD_ALIASES.items():
        if src in adapted and src not in remote_map and dst in remote_map:
            adapted[dst] = adapted.pop(src)
    for name in list(adapted):
        meta = remote_map.get(name)
        if meta is None:
            adapted.pop(name)
            continue
        f_type = meta.get("type")
        ui_type = str(meta.get("ui_type") or "")
        is_single_select = f_type == 3 or ui_type == "SingleSelect"
        if is_single_select and isinstance(adapted[name], list):
            adapted[name] = adapted[name][0] if adapted[name] else None
            if adapted[name] is None:
                adapted.pop(name)
    return adapted


async def create_validation_record_in_feishu(
    db: AsyncSession,
    payload: dict[str, Any],
    year: int | None = None,
) -> dict[str, Any]:
    """在飞书中创建验证记录。year 指定时写入对应年度表。"""
    title = str(payload.get("title") or "").strip()
    if not title:
        raise AppException(message="确认名称不能为空")
    validation_type = str(payload.get("validation_type") or "").strip()
    entity_code = _entity_code_for_validation_type(validation_type, year)
    fields = await _build_validation_feishu_fields(db, payload)
    fields = await _adapt_validation_fields_to_remote(db, entity_code, fields)
    created = await _create_entity_record(
        db,
        entity_code,
        fields,
        search_conditions=[("确认名称", title)],
    )
    await _invalidate_validation_list_cache(entity_code)
    return await get_validation_record_from_feishu(
        db, created["record_id"], validation_type, year
    )


async def update_validation_record_in_feishu(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
    validation_type: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """更新飞书中的验证记录。"""
    entity_code = _entity_code_for_validation_type(validation_type, year)

    current = await get_validation_record_from_feishu(
        db, record_id, validation_type, year
    )
    merged = {**current, **payload}
    title = str(merged.get("title") or "").strip()
    if not title:
        raise AppException(message="飞书验证记录缺少确认名称")

    fields = await _build_validation_feishu_fields(db, merged)
    fields = await _adapt_validation_fields_to_remote(db, entity_code, fields)
    await _update_entity_record(
        db,
        entity_code,
        record_id,
        fields,
        search_conditions=[("确认名称", title)],
    )
    await _invalidate_validation_list_cache(entity_code)
    return await get_validation_record_from_feishu(
        db, record_id, validation_type, year
    )


async def delete_validation_record_in_feishu(
    db: AsyncSession,
    record_id: str,
    validation_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    year: int | None = None,
) -> None:
    """删除飞书中的验证记录。"""
    entity_code = _entity_code_for_validation_type(validation_type, year)

    await _delete_entity_record(db, entity_code, record_id, actor_user_id)
    await _invalidate_validation_list_cache(entity_code)


async def pull_validation_records_from_feishu(
    db: AsyncSession,
    validation_type: str | None = None,
    year: int | None = None,
) -> dict[str, int]:
    """从飞书拉取验证记录并返回拉取结果。"""
    entity_code = _entity_code_for_validation_type(validation_type, year)

    try:
        _, _entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    except AppException:
        return {"synced": 0, "failed": 0}

    synced = 0
    failed = 0

    try:
        result = await list_validation_records_from_feishu(
            db,
            validation_type=validation_type,
            year=year,
            page=1,
            page_size=10000,
        )
    except Exception:
        return {"synced": 0, "failed": 0}
    synced = len(result.get("items", []))
    failed = 0
    return {"synced": synced, "failed": failed}


async def get_validation_statistics_from_feishu(
    db: AsyncSession,
) -> dict[str, Any]:
    """从飞书获取验证统计数据。"""
    try:
        result = await list_validation_records_from_feishu(
            db,
            page=1,
            page_size=10000,
        )
    except Exception:
        return {
            "total": 0,
            "typeDistribution": [],
            "statusDistribution": [],
            "executionDistribution": [],
            "revalidationUpcoming": 0,
        }

    items = result.get("items", [])
    total = len(items)

    # 按验证类别分组
    type_counts: dict[str, int] = {}
    for item in items:
        vtype = item.get("validation_type") or "unknown"
        type_counts[vtype] = type_counts.get(vtype, 0) + 1
    type_distribution = [
        {"validation_type": k, "count": v} for k, v in type_counts.items()
    ]

    # 按状态分组
    status_counts: dict[str, int] = {}
    for item in items:
        status = item.get("status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    status_distribution = [{"status": k, "count": v} for k, v in status_counts.items()]

    # 执行子表分布（按验证类别）
    execution_distribution = [
        {"validation_type": k, "count": v} for k, v in type_counts.items()
    ]

    # 近期待再验证（30 天内到期）
    from datetime import date, timedelta

    upcoming_deadline = date.today() + timedelta(days=30)
    revalidation_upcoming = 0
    for item in items:
        planned_end = item.get("planned_end_date")
        if planned_end:
            try:
                end_date = date.fromisoformat(planned_end)
                if end_date <= upcoming_deadline:
                    revalidation_upcoming += 1
            except (ValueError, TypeError):
                pass

    return {
        "total": total,
        "typeDistribution": type_distribution,
        "statusDistribution": status_distribution,
        "executionDistribution": execution_distribution,
        "revalidationUpcoming": revalidation_upcoming,
    }


# ============ CAPA 台账 / CAPA 计划跟踪 Feishu Sync ============


async def sync_capas_from_feishu(db: AsyncSession) -> dict[str, int]:
    """Pull all records from the Feishu Bitable ``capa_ledger`` table and
    upsert them into the local ``CAPA`` table.

    Each Feishu record is matched by ``capa_code``:
    - If a local CAPA with the same ``capa_code`` exists, it is updated.
    - Otherwise a new CAPA row is created.

    Returns ``{"synced": N, "failed": N}``.
    """
    synced = 0
    failed = 0

    try:
        _, _entity = await _resolve_runtime_entity(db, "capa_ledger", direction="pull")
    except AppException:
        logger.exception("capa_ledger 飞书 Base 未启用，无法同步 CAPA 台账")
        return {"synced": 0, "failed": 0}

    try:
        records = await _search_entity_records(db, "capa_ledger")
    except Exception:
        logger.exception("从飞书拉取 CAPA 台账记录失败")
        return {"synced": 0, "failed": 0}

    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime

    for record in records:
        try:
            fields = record.get("fields") or {}

            capa_code = normalize_text(fields.get("CAPA编号"))
            if not capa_code:
                failed += 1
                continue

            status = normalize_text(fields.get("CAPA状态"))
            title = normalize_text(fields.get("CAPA简述"))
            department = normalize_text(fields.get("事件部门"))
            affected_product = normalize_text(fields.get("涉及产品"))
            evaluation_result = normalize_text(fields.get("CAPA效果评估"))
            qa_confirmer = normalize_text(fields.get("QA质量员"))

            closure_date = parse_datetime(fields.get("关闭日期"))
            qa_confirm_date = parse_datetime(fields.get("QA质量员确认日期"))
            expected_completion_date = parse_datetime(fields.get("启动日期"))

            feishu_record_id = str(record.get("record_id") or "")
            sync_at = datetime.now(UTC)

            existing = await repository.get_capa_by_code(db, capa_code)

            if existing:
                existing.title = title
                existing.status = status or existing.status
                existing.department = department
                existing.affected_product = affected_product
                existing.evaluation_result = evaluation_result
                existing.closure_date = closure_date
                existing.qa_confirmer = qa_confirmer
                existing.qa_confirm_date = qa_confirm_date
                existing.expected_completion_date = expected_completion_date
                existing.feishu_base_record_id = feishu_record_id or None
                existing.feishu_sync_status = "synced"
                existing.feishu_synced_at = sync_at
                existing.feishu_last_sync_direction = "base_to_system"
                existing.feishu_last_sync_error = None
                existing.updated_at = sync_at
            else:
                capa = CAPA(
                    capa_code=capa_code,
                    title=title,
                    status=status or "draft",
                    department=department,
                    affected_product=affected_product,
                    evaluation_result=evaluation_result,
                    closure_date=closure_date,
                    qa_confirmer=qa_confirmer,
                    qa_confirm_date=qa_confirm_date,
                    expected_completion_date=expected_completion_date,
                    feishu_base_record_id=feishu_record_id or None,
                    feishu_sync_status="synced",
                    feishu_synced_at=sync_at,
                    feishu_last_sync_direction="base_to_system",
                )
                db.add(capa)

            await db.commit()
            synced += 1
        except Exception:
            try:
                await db.rollback()
            except Exception:
                logger.warning("rollback 失败", exc_info=True)
            logger.exception("同步 CAPA 台账记录失败: %s", record.get("record_id"))
            failed += 1

    return {"synced": synced, "failed": failed}


async def sync_capa_plan_tracks_from_feishu(db: AsyncSession) -> dict[str, int]:
    """Pull all records from the Feishu Bitable ``capa_plan_track`` table and
    upsert them into the local ``CapaPlanTrack`` table.

    Each Feishu record is matched by ``capa_code`` + ``plan_content``:
    - If a local track with the same key exists, it is updated.
    - Otherwise a new ``CapaPlanTrack`` row is created.

    Records whose ``capa_code`` does not correspond to an existing local
    CAPA row are skipped (counted as ``failed``) because ``capa_id`` is
    a non-nullable foreign key.

    Returns ``{"synced": N, "failed": N}``.
    """
    synced = 0
    failed = 0

    try:
        _, _entity = await _resolve_runtime_entity(
            db, "capa_plan_track", direction="pull"
        )
    except AppException:
        logger.exception("capa_plan_track 飞书 Base 未启用，无法同步 CAPA 计划跟踪")
        return {"synced": 0, "failed": 0}

    try:
        records = await _search_entity_records(db, "capa_plan_track")
    except Exception:
        logger.exception("从飞书拉取 CAPA 计划跟踪记录失败")
        return {"synced": 0, "failed": 0}

    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    normalize_bool = feishu_sync_service._normalize_bool_from_yes_no

    for record in records:
        try:
            fields = record.get("fields") or {}

            capa_code = normalize_text(fields.get("CAPA编号"))
            plan_content = normalize_text(fields.get("计划内容"))
            if not capa_code or not plan_content:
                failed += 1
                continue

            owner_name = normalize_text(fields.get("责任人"))
            department_head = normalize_text(fields.get("部门负责人"))
            progress = normalize_text(fields.get("进度"))
            reminder_status = normalize_text(fields.get("提醒状态"))

            owner_confirmed = bool(normalize_bool(fields.get("责任人确认")))
            department_head_confirmed = bool(
                normalize_bool(fields.get("部门负责人确认"))
            )

            due_datetime = parse_datetime(fields.get("完成时间"))
            due_date = due_datetime.date() if due_datetime else None

            feishu_record_id = str(record.get("record_id") or "")
            sync_at = datetime.now(UTC)

            capa = await repository.get_capa_by_code(db, capa_code)
            if not capa:
                failed += 1
                continue

            result = await db.execute(
                select(CapaPlanTrack).where(
                    CapaPlanTrack.capa_code == capa_code,
                    CapaPlanTrack.plan_content == plan_content,
                    CapaPlanTrack.is_deleted.is_(False),
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.capa_id = capa.id
                existing.due_date = due_date
                existing.owner_name = owner_name
                existing.owner_confirmed = owner_confirmed
                existing.department_head = department_head
                existing.department_head_confirmed = department_head_confirmed
                existing.progress = progress
                existing.reminder_status = reminder_status or existing.reminder_status
                existing.feishu_base_record_id = feishu_record_id or None
                existing.feishu_sync_status = "synced"
                existing.feishu_synced_at = sync_at
                existing.feishu_last_sync_direction = "base_to_system"
                existing.feishu_last_sync_error = None
                existing.updated_at = sync_at
            else:
                track = CapaPlanTrack(
                    capa_id=capa.id,
                    capa_code=capa_code,
                    plan_content=plan_content,
                    due_date=due_date,
                    owner_name=owner_name,
                    owner_confirmed=owner_confirmed,
                    department_head=department_head,
                    department_head_confirmed=department_head_confirmed,
                    progress=progress,
                    reminder_status=reminder_status or "pending",
                    feishu_base_record_id=feishu_record_id or None,
                    feishu_sync_status="synced",
                    feishu_synced_at=sync_at,
                    feishu_last_sync_direction="base_to_system",
                )
                db.add(track)

            await db.commit()
            synced += 1
        except Exception:
            try:
                await db.rollback()
            except Exception:
                logger.warning("rollback 失败", exc_info=True)
            logger.exception("同步 CAPA 计划跟踪记录失败: %s", record.get("record_id"))
            failed += 1

    return {"synced": synced, "failed": failed}
