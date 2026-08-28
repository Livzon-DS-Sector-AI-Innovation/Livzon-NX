"""Supplier Qualification Feishu pages service.

Operates directly on Feishu Bitable for supplier qualification management.
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

ENTITY_SUPPLIER_QUALIFICATION = "supplier_qualification"


def _map_nested_user(value: Any) -> str | None:
    return feishu_sync_service._normalize_text(value)


def _map_checkbox(value: Any) -> bool:
    return value is True or str(value).strip().lower() in ("true", "是", "已确认", "1")


def _map_supplier_qualification(
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

    # 负责人 - user field
    responsible_raw = field_value(entity, fields, "负责人")
    responsible: str | None = None
    if isinstance(responsible_raw, list):
        names = []
        for item in responsible_raw:
            if isinstance(item, dict):
                name = item.get("name", "") or item.get("text", "")
                if name:
                    names.append(name)
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        responsible = "、".join(names) if names else None
    elif responsible_raw:
        responsible = normalize_text(responsible_raw)

    # 到期状态 - formula, read-only
    expiry_status = normalize_text(field_value(entity, fields, "到期状态"))

    return {
        "record_id": str(record.get("record_id") or ""),
        "supplier_name": normalize_text(field_value(entity, fields, "供应商名称")),
        "material_name": normalize_text(field_value(entity, fields, "物料名称")),
        "material_type": normalize_text(field_value(entity, fields, "物料类型")),
        "qualification_name": normalize_text(field_value(entity, fields, "资质名称")),
        "qualification_file": normalize_text(field_value(entity, fields, "资质文件")),
        "is_completed": _map_checkbox(field_value(entity, fields, "是否完成")),
        "deadline": (lambda dt: dt.isoformat() if dt else None)(
            parse_datetime(field_value(entity, fields, "截止日期"))
        ),
        "responsible_person": responsible,
        "remark": normalize_text(field_value(entity, fields, "备注")),
        "expiry_status": expiry_status,
        "created_at": created_at,
        "updated_at": modified_at or created_at,
    }


async def list_supplier_qualification_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    supplier_name: str | None = None,
    material_type: str | None = None,
    qualification_name: str | None = None,
    is_completed: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="pull"
    )
    records = await _search_entity_records(db, ENTITY_SUPPLIER_QUALIFICATION)
    items = [_map_supplier_qualification(record, entity) for record in records]

    if keyword:
        kw = keyword.lower()
        items = [
            item
            for item in items
            if any(
                kw in (str(item.get(f) or "")).lower()
                for f in (
                    "supplier_name",
                    "material_name",
                    "material_type",
                    "qualification_name",
                    "qualification_file",
                    "responsible_person",
                    "remark",
                )
            )
        ]

    if supplier_name:
        items = [item for item in items if item.get("supplier_name") == supplier_name]
    if material_type:
        items = [item for item in items if item.get("material_type") == material_type]
    if qualification_name:
        items = [
            item
            for item in items
            if item.get("qualification_name") == qualification_name
        ]
    if is_completed is not None:
        items = [item for item in items if item.get("is_completed") == is_completed]

    # Sort by deadline or updated_at (handle mixed types: str vs datetime)
    def _sort_key(x: Any) -> Any:
        deadline = x.get("deadline")
        updated = x.get("updated_at")
        # Convert to comparable format
        if deadline and isinstance(deadline, str):
            return deadline
        if deadline and isinstance(deadline, datetime):
            return deadline.isoformat()
        if updated and isinstance(updated, datetime):
            return updated.isoformat()
        return ""

    items.sort(key=_sort_key, reverse=True)
    start = (page - 1) * page_size
    return _build_page_result(
        items[start : start + page_size], len(items), page, page_size
    )


async def get_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="pull"
    )
    # 优先用 get_record 直接获取单条（避免搜索索引延迟）
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    record = await client.get_record(
        feishu_sync_service._require_table_id(entity), record_id
    )
    if record:
        return _map_supplier_qualification(record, entity)
    # fallback: 搜索
    records = await _search_entity_records(db, ENTITY_SUPPLIER_QUALIFICATION)
    for rec in records:
        if str(rec.get("record_id") or "") == record_id:
            return _map_supplier_qualification(rec, entity)
    raise NotFoundException(resource="供应商资质记录")


def _build_supplier_qualification_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    text_fields: list[tuple[str, str]] = [
        ("供应商名称", "supplier_name"),
        ("物料名称", "material_name"),
        ("物料类型", "material_type"),
        ("资质名称", "qualification_name"),
        ("资质文件", "qualification_file"),
        ("备注", "remark"),
    ]
    for feishu_key, payload_key in text_fields:
        val = str(payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    # Checkbox
    is_completed = payload.get("is_completed")
    if is_completed is not None:
        fields["是否完成"] = bool(is_completed)

    # Date
    deadline = payload.get("deadline")
    if deadline not in (None, ""):
        fields["截止日期"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(deadline)
        )

    # User field - 负责人
    responsible = payload.get("responsible_person")
    if responsible:
        if isinstance(responsible, dict) and responsible.get("id"):
            fields["负责人"] = [responsible]
        elif isinstance(responsible, str) and responsible.strip():
            if responsible.strip().startswith("ou_"):
                fields["负责人"] = [{"id": responsible.strip()}]

    return fields


async def create_supplier_qualification_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    supplier_name = str(payload.get("supplier_name") or "").strip()
    if not supplier_name:
        raise AppException(message="供应商名称不能为空")
    qualification_name = str(payload.get("qualification_name") or "").strip()
    if not qualification_name:
        raise AppException(message="资质名称不能为空")
    fields = _build_supplier_qualification_fields(payload)
    created = await _create_entity_record(db, ENTITY_SUPPLIER_QUALIFICATION, fields)
    return await get_supplier_qualification_record(db, created["record_id"])


async def update_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_supplier_qualification_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_supplier_qualification_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    await client.update_record(
        feishu_sync_service._require_table_id(entity), record_id, fields
    )
    return await get_supplier_qualification_record(db, record_id)


async def delete_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_SUPPLIER_QUALIFICATION, record_id)


async def pull_supplier_qualification_records(db: AsyncSession) -> dict[str, int]:
    try:
        _, _entity = await _resolve_runtime_entity(
            db, ENTITY_SUPPLIER_QUALIFICATION, direction="pull"
        )
    except AppException:
        return {"synced": 0, "failed": 0}
    try:
        result = await list_supplier_qualification_records(db, page=1, page_size=10000)
    except Exception:
        return {"synced": 0, "failed": 0}
    return {"synced": len(result.get("items", [])), "failed": 0}


async def get_supplier_statistics(db: AsyncSession) -> dict[str, Any]:
    """Get supplier qualification dashboard statistics with GMP metrics."""
    try:
        result = await list_supplier_qualification_records(db, page=1, page_size=99999)
    except AppException:
        return _empty_supplier_stats()
    items: list[dict[str, Any]] = result.get("items", [])

    total = len(items)
    completed = sum(1 for item in items if item.get("is_completed"))
    pending = total - completed

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)

    # 供应商维度的统计
    supplier_stats: dict[
        str, dict[str, int]
    ] = {}  # {name: {total, completed, pending, expired, due30, due60, due90}}
    material_type_stats: dict[
        str, dict[str, int]
    ] = {}  # {type: {total, completed, pending, expired}}
    qualification_stats: dict[
        str, dict[str, int]
    ] = {}  # {name: {total, completed, pending}}

    expired_count = 0
    due_30_count = 0
    due_60_count = 0
    due_90_count = 0
    normal_count = 0

    for item in items:
        sn = (item.get("supplier_name") or "未知").strip()
        mt = (item.get("material_type") or "未知").strip()
        qn = (item.get("qualification_name") or "未知").strip()
        is_done = item.get("is_completed")

        # Supplier stats
        if sn not in supplier_stats:
            supplier_stats[sn] = {
                "total": 0,
                "completed": 0,
                "pending": 0,
                "expired": 0,
                "due30": 0,
                "due60": 0,
                "due90": 0,
            }
        supplier_stats[sn]["total"] += 1
        supplier_stats[sn]["completed" if is_done else "pending"] += 1

        # Material type stats
        if mt not in material_type_stats:
            material_type_stats[mt] = {
                "total": 0,
                "completed": 0,
                "pending": 0,
                "expired": 0,
            }
        material_type_stats[mt]["total"] += 1
        material_type_stats[mt]["completed" if is_done else "pending"] += 1

        # Qualification stats
        if qn not in qualification_stats:
            qualification_stats[qn] = {"total": 0, "completed": 0, "pending": 0}
        qualification_stats[qn]["total"] += 1
        qualification_stats[qn]["completed" if is_done else "pending"] += 1

        # Expiry analysis
        deadline = item.get("deadline")
        if deadline:
            if isinstance(deadline, str):
                deadline = feishu_sync_service._parse_feishu_datetime(deadline)
            if deadline:
                days_left = (deadline - now).days
                if days_left < 0:
                    expired_count += 1
                    supplier_stats[sn]["expired"] += 1
                    material_type_stats[mt]["expired"] += 1
                elif days_left <= 30:
                    due_30_count += 1
                    supplier_stats[sn]["due30"] += 1
                elif days_left <= 60:
                    due_60_count += 1
                    supplier_stats[sn]["due60"] += 1
                elif days_left <= 90:
                    due_90_count += 1
                    supplier_stats[sn]["due90"] += 1
                else:
                    normal_count += 1
            else:
                normal_count += 1
        else:
            normal_count += 1

    # 供应商风险排名（按过期+待完成排序，取前10）
    supplier_risk = sorted(
        [
            {
                "name": k,
                "total": v["total"],
                "completed": v["completed"],
                "pending": v["pending"],
                "expired": v["expired"],
                "due30": v["due30"],
                "risk_score": v["expired"] * 3 + v["due30"] * 2 + v["pending"],
            }
            for k, v in supplier_stats.items()
        ],
        key=lambda x: -float(str(x["risk_score"])),
    )[:10]

    # 物料类型合规率
    material_type_compliance = [
        {
            "type": k,
            "total": v["total"],
            "completed": v["completed"],
            "pending": v["pending"],
            "expired": v["expired"],
            "compliance_rate": round(v["completed"] / v["total"] * 100, 1)
            if v["total"] > 0
            else 0,
        }
        for k, v in sorted(material_type_stats.items(), key=lambda x: -x[1]["total"])
    ]

    # 资质类型完成率
    qualification_compliance = [
        {
            "name": k,
            "total": v["total"],
            "completed": v["completed"],
            "pending": v["pending"],
            "completion_rate": round(v["completed"] / v["total"] * 100, 1)
            if v["total"] > 0
            else 0,
        }
        for k, v in sorted(qualification_stats.items(), key=lambda x: -x[1]["total"])
    ]

    # 到期趋势（按截止日期月份汇总）
    expiry_timeline: dict[str, int] = {}
    for item in items:
        deadline = item.get("deadline")
        if deadline:
            if isinstance(deadline, str):
                deadline = feishu_sync_service._parse_feishu_datetime(deadline)
            if deadline:
                month_key = deadline.strftime("%Y-%m")
                expiry_timeline[month_key] = expiry_timeline.get(month_key, 0) + 1

    timeline_sorted = sorted(expiry_timeline.items())
    # 只取最近12个月 + 未来12个月
    recent_timeline = [
        {"month": k, "count": v}
        for k, v in timeline_sorted
        if k <= (now + timedelta(days=400)).strftime("%Y-%m")
    ][-24:]

    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "expired_count": expired_count,
        "due_30_count": due_30_count,
        "due_60_count": due_60_count,
        "due_90_count": due_90_count,
        "normal_count": normal_count,
        "supplier_count": len(supplier_stats),
        "material_type_compliance": material_type_compliance,
        "qualification_compliance": qualification_compliance,
        "supplier_risk_ranking": supplier_risk,
        "expiry_timeline": recent_timeline,
    }


def _empty_supplier_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "completion_rate": 0,
        "expired_count": 0,
        "due_30_count": 0,
        "due_60_count": 0,
        "due_90_count": 0,
        "normal_count": 0,
        "supplier_count": 0,
        "material_type_compliance": [],
        "qualification_compliance": [],
        "supplier_risk_ranking": [],
        "expiry_timeline": [],
    }
