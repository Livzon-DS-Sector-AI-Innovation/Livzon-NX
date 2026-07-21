"""Quality management business logic."""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import (
    AttachmentReview,
    CAPA,
    ChangeActionPlan,
    ChangeControl,
    DepartmentContact,
    DepartmentWeeklyConfirmation,
    Deviation,
)
from app.modules.quality import repository
from app.modules.quality.schemas import (
    DepartmentContactOut,
    DepartmentWeeklyConfirmationOut,
    AttachmentReviewOut,
    CapaApprovalRequest,
    CapaDetail,
    CapaListItem,
    CapaStatistics,
    ChangeDetail,
    ChangeListItem,
    ChangeStatistics,
    ConfirmProductionStatusRequest,
    CreateCapaRequest,
    CreateChangeRequest,
    CreateDepartmentContactRequest,
    CreateDeviationRequest,
    DeviationDetail,
    DeviationListItem,
    DeviationReportRecordListItem,
    DeviationStatistics,
    SubmitInvestigationRequest,
    SubmitReviewRequest,
    UpdateCapaRequest,
    UpdateChangeRequest,
    UpdateDepartmentContactRequest,
    UpdateDeviationRequest,
)
from app.platform.identity.models import User


MONTHLY_DEVIATION_CODE_PATTERN = re.compile(r"^PC-(\d{4})(\d{3})$")

# Workflow constants
APPROVAL_STEP_ORDER = [
    "ai_analysis",
    "investigation",
    "dept_head_review",
    "cross_dept_head_review",
    "qa_review",
    "qa_head_review",
    "quality_head_review",
]

APPROVAL_STEP_LABELS = {
    "ai_analysis": "AI分析",
    "investigation": "调查",
    "dept_head_review": "部门负责人审核",
    "cross_dept_head_review": "跨部门负责人审核",
    "qa_review": "所属QA审核",
    "qa_head_review": "QA负责人审核",
    "quality_head_review": "质量负责人审核",
}

STATUS_TO_STEP = {
    "pending_ai_analysis": "ai_analysis",
    "pending_investigation": "investigation",
    "pending_dept_head_review": "dept_head_review",
    "pending_cross_dept_head_review": "cross_dept_head_review",
    "pending_qa_review": "qa_review",
    "pending_qa_head_review": "qa_head_review",
    "pending_quality_head_review": "quality_head_review",
}

STEP_TO_NEXT_STATUS = {
    "ai_analysis": "pending_investigation",
    "investigation": "pending_dept_head_review",
    "dept_head_review": "pending_cross_dept_head_review",
    "cross_dept_head_review": "pending_qa_review",
    "qa_review": "pending_qa_head_review",
    "qa_head_review": "pending_quality_head_review",
    "quality_head_review": "pending_final_code",
}

STEP_ROLE_LABELS = {
    "ai_analysis": "AI系统",
    "investigation": "调查人",
    "dept_head_review": "部门负责人",
    "cross_dept_head_review": "跨部门负责人",
    "qa_review": "所属QA",
    "qa_head_review": "QA负责人",
    "quality_head_review": "质量负责人",
}

STATUS_TO_PENDING = {
    "ai_analysis": "pending_ai_analysis",
    "investigation": "pending_investigation",
    "dept_head_review": "pending_dept_head_review",
    "cross_dept_head_review": "pending_cross_dept_head_review",
    "qa_review": "pending_qa_review",
    "qa_head_review": "pending_qa_head_review",
    "quality_head_review": "pending_quality_head_review",
}


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


def _build_page_result(
    items: list[dict[str, Any]], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _build_change_list_items(
    db: AsyncSession, items: list[ChangeControl]
) -> list[dict[str, Any]]:
    plan_counts = await repository.get_change_action_plan_counts_by_change_ids(
        db, [item.id for item in items]
    )

    item_dicts: list[dict[str, Any]] = []
    for item in items:
        item_dict = ChangeListItem.model_validate(item).model_dump()
        item_dict["action_plan_count"] = plan_counts.get(str(item.id), 0)
        item_dicts.append(item_dict)
    return item_dicts


async def _build_deviation_list_items(
    db: AsyncSession, items: list[Deviation]
) -> list[dict[str, Any]]:
    item_dicts: list[dict[str, Any]] = []
    for item in items:
        item_dict = DeviationListItem.model_validate(item).model_dump()
        related_capas = await repository.get_related_capas_for_deviation(
            db, item.id, item.deviation_code
        )
        item_dict["related_capa_codes"] = [capa.capa_code for capa in related_capas]
        item_dict["related_capas"] = [
            {"id": capa.id, "capa_code": capa.capa_code} for capa in related_capas
        ]
        item_dict["close_time"] = (
            item.status_updated_at if item.status == "closed" else None
        )
        item_dicts.append(item_dict)
    return item_dicts


def _pick_report_status(
    item: dict[str, Any],
) -> str | None:
    return (
        item.get("report_status")
        or item.get("qa_head_result")
        or item.get("qa_result")
        or item.get("department_head_result")
        or item.get("status")
    )


async def _build_deviation_report_record_items_from_feishu(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    report_entity = runtime.get_entity_config("deviation_report_record", direction="pull")
    if not runtime.is_enabled() or not report_entity:
        return _build_page_result([], 0, page, page_size)

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_report_record",
        None,
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    normalize_review_result = feishu_sync_service._normalize_review_result
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    deviation_codes = [
        normalize_text(field_value(report_entity, record.get("fields") or {}, "偏差编号"))
        for record in records
    ]
    linked_deviations = await repository.get_deviations_by_codes(
        db, [code for code in deviation_codes if code]
    )
    deviation_map = {
        deviation.deviation_code: deviation for deviation in linked_deviations
    }

    items: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        deviation_code = normalize_text(field_value(report_entity, fields, "偏差编号"))
        linked_deviation = (
            deviation_map.get(deviation_code) if deviation_code else None
        )
        item = DeviationReportRecordListItem(
            id=record.get("record_id", ""),
            deviation_id=linked_deviation.id if linked_deviation else None,
            deviation_code=deviation_code,
            report_time=parse_datetime(field_value(report_entity, fields, "报告时间")),
            description=normalize_text(field_value(report_entity, fields, "偏差内容")),
            report_document=normalize_text(field_value(report_entity, fields, "偏差报告")),
            product_batch=normalize_text(
                field_value(report_entity, fields, "涉及产品名称/批号")
            ),
            department=normalize_text(field_value(report_entity, fields, "部门")),
            reporter_name=normalize_text(field_value(report_entity, fields, "报告人")),
            department_head=normalize_text(
                field_value(report_entity, fields, "部门负责人")
            ),
            department_head_result=normalize_review_result(
                field_value(report_entity, fields, "部门负责人确认")
            ),
            department_head_reviewed_at=parse_datetime(
                field_value(report_entity, fields, "部门负责人确认时间")
            ),
            qa_name=normalize_text(field_value(report_entity, fields, "QA")),
            qa_result=normalize_review_result(
                field_value(report_entity, fields, "QA确认")
            ),
            qa_reviewed_at=parse_datetime(
                field_value(report_entity, fields, "QA确认时间")
            ),
            qa_head_name=normalize_text(
                field_value(report_entity, fields, "QA负责人")
            ),
            qa_head_result=normalize_review_result(
                field_value(report_entity, fields, "QA负责人确认")
            ),
            qa_head_reviewed_at=parse_datetime(
                field_value(report_entity, fields, "QA负责人确认时间")
            ),
            report_status=normalize_text(
                field_value(report_entity, fields, "报告状态")
            ),
            feishu_base_table_id=report_entity.table_id,
            feishu_base_record_id=record.get("record_id"),
            feishu_sync_status="synced",
            feishu_last_sync_error=None,
            feishu_last_sync_direction="base_to_system",
            feishu_synced_at=get_record_modified_at(record),
            feishu_source_updated_at=get_record_modified_at(record),
        ).model_dump()
        item["report_status"] = _pick_report_status(item)
        items.append(item)

    items.sort(
        key=lambda item: (
            item.get("report_time") or datetime.min.replace(tzinfo=timezone.utc),
            item.get("feishu_source_updated_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    start = (page - 1) * page_size
    end = start + page_size
    return _build_page_result(items[start:end], len(items), page, page_size)


async def _get_deviation_report_record_from_feishu(
    db: AsyncSession,
    feishu_record_id: str,
) -> tuple[dict[str, Any], Any, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    report_entity = runtime.get_entity_config("deviation_report_record", direction="pull")
    if not runtime.is_enabled() or not report_entity:
        raise ValueError("报告记录飞书 Base 未启用")

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_report_record",
        None,
    )
    for record in records:
        if str(record.get("record_id") or "") == feishu_record_id:
            return record, report_entity, feishu_sync_service
    raise ValueError("飞书报告记录不存在")


async def ensure_deviation_from_report_record(
    db: AsyncSession,
    feishu_record_id: str,
) -> dict[str, Any]:
    record, report_entity, feishu_sync_service = await _get_deviation_report_record_from_feishu(
        db,
        feishu_record_id,
    )
    fields = record.get("fields") or {}
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime
    get_record_modified_at = feishu_sync_service._get_record_modified_at

    deviation_code = normalize_text(field_value(report_entity, fields, "偏差编号"))
    if not deviation_code:
        raise ValueError("飞书报告记录缺少偏差编号")

    description = normalize_text(field_value(report_entity, fields, "偏差内容"))
    report_content = normalize_text(field_value(report_entity, fields, "偏差报告"))
    product_batch = normalize_text(field_value(report_entity, fields, "涉及产品名称/批号"))
    department = normalize_text(field_value(report_entity, fields, "部门"))
    reporter_name = normalize_text(field_value(report_entity, fields, "报告人"))
    report_time = parse_datetime(field_value(report_entity, fields, "报告时间"))
    source_updated_at = get_record_modified_at(record)

    result = await db.execute(
        select(Deviation).where(
            Deviation.feishu_base_record_id == feishu_record_id,
            Deviation.is_deleted == False,
        )
    )
    deviation = result.scalar_one_or_none()
    created = False
    if not deviation:
        deviation = await repository.get_deviation_by_code(db, deviation_code)

    payload = {
        "deviation_code": deviation_code,
        "title": description or deviation_code,
        "department": department,
        "discovery_date": report_time,
        "description": description,
        "report_content": report_content,
        "affected_items": product_batch,
        "discoverer": reporter_name,
    }

    if not deviation:
        try:
            deviation = await repository.create_deviation(
                db,
                {
                    **payload,
                    "status": "draft",
                },
            )
            created = True
        except IntegrityError:
            await db.rollback()
            deviation = await repository.get_deviation_by_code(db, deviation_code)
            if not deviation:
                raise
    else:
        await repository.update_deviation(db, deviation, payload)

    await feishu_sync_service._mark_sync_success(
        db,
        deviation,
        table_id=report_entity.table_id,
        record_id=feishu_record_id,
        direction="base_to_system",
        source_updated_at=source_updated_at,
    )
    return {
        "deviation_id": str(deviation.id),
        "deviation_code": deviation.deviation_code,
        "created": created,
    }


async def sync_deviation_report_record_to_feishu_by_ref(
    db: AsyncSession,
    record_ref: str,
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    deviation_id: uuid.UUID | None = None
    try:
        candidate = uuid.UUID(record_ref)
    except ValueError:
        candidate = None
    if candidate:
        deviation = await repository.get_deviation_by_id(db, candidate)
        if deviation:
            deviation_id = candidate

    if deviation_id is None:
        ensured = await ensure_deviation_from_report_record(db, record_ref)
        deviation_id = uuid.UUID(ensured["deviation_id"])
        return await feishu_sync_service.sync_deviation_report_record_to_feishu(
            db,
            deviation_id,
            target_record_id=record_ref,
        )

    return await feishu_sync_service.sync_deviation_report_record_to_feishu(
        db,
        deviation_id,
    )


async def _search_deviation_report_record_codes_from_feishu(
    db: AsyncSession,
) -> list[str]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    report_entity = runtime.get_entity_config("deviation_report_record", direction="pull")
    if not runtime.is_enabled() or not report_entity:
        raise ValueError("无法从飞书报告记录表生成偏差编号")

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_report_record",
        None,
    )
    field_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text

    codes: list[str] = []
    for record in records:
        fields = record.get("fields") or {}
        code = normalize_text(field_value(report_entity, fields, "偏差编号"))
        if code:
            codes.append(code)
    return codes


async def _generate_monthly_deviation_code(
    db: AsyncSession,
    now: datetime,
) -> str:
    prefix = f"PC-{now.strftime('%y%m')}"
    try:
        codes = await _search_deviation_report_record_codes_from_feishu(db)
    except Exception as exc:  # pragma: no cover - guarded by tests below
        raise ValueError("无法从飞书报告记录表生成偏差编号") from exc

    max_sequence = 0
    for code in codes:
        match = MONTHLY_DEVIATION_CODE_PATTERN.match(code)
        if not match:
            continue
        code_prefix, sequence = match.groups()
        if f"PC-{code_prefix}" != prefix:
            continue
        max_sequence = max(max_sequence, int(sequence))
    return f"{prefix}{max_sequence + 1:03d}"
async def _build_capa_list_items(
    db: AsyncSession, items: list[CAPA]
) -> list[dict[str, Any]]:
    tracks = await repository.get_capa_plan_tracks_by_capa_ids(
        db, [item.id for item in items]
    )
    track_map: dict[str, list[str]] = {}
    track_refs_map: dict[str, list[dict[str, Any]]] = {}
    for track in tracks:
        key = str(track.capa_id)
        track_map.setdefault(key, []).append(track.plan_content)
        track_refs_map.setdefault(key, []).append(
            {"id": track.id, "plan_content": track.plan_content}
        )

    item_dicts: list[dict[str, Any]] = []
    for item in items:
        item_dict = CapaListItem.model_validate(item).model_dump()
        item_dict["linked_plan_contents"] = track_map.get(str(item.id), [])
        item_dict["linked_plan_tracks"] = track_refs_map.get(str(item.id), [])
        item_dicts.append(item_dict)
    return item_dicts

# ============ Deviation Service ============
async def get_deviation_list(
    db: AsyncSession,
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
    deviation_code: str | None = None,
    product_keyword: str | None = None,
    has_occurred_before: bool | None = None,
    is_closed: bool | None = None,
    investigation_completed_from: str | None = None,
    investigation_completed_to: str | None = None,
    root_cause_keyword: str | None = None,
    corrective_actions_keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    items, total = await repository.get_deviations(
        db,
        status=status,
        level=level,
        department=department,
        keyword=keyword,
        page=page,
        page_size=page_size,
        deviation_code=deviation_code,
        product_keyword=product_keyword,
        has_occurred_before=has_occurred_before,
        is_closed=is_closed,
        investigation_completed_from=_parse_datetime_filter(
            investigation_completed_from
        ),
        investigation_completed_to=_parse_datetime_filter_end_exclusive(
            investigation_completed_to
        ),
        root_cause_keyword=root_cause_keyword,
        corrective_actions_keyword=corrective_actions_keyword,
    )

    return _build_page_result(
        await _build_deviation_list_items(db, items),
        total,
        page,
        page_size,
    )


async def get_deviation_report_record_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    try:
        result = await _build_deviation_report_record_items_from_feishu(
            db,
            page=page,
            page_size=page_size,
        )
        if result["total"] > 0:
            return result
    except Exception:
        pass

    query = select(Deviation).where(Deviation.is_deleted == False)
    count_query = select(func.count()).select_from(Deviation).where(
        Deviation.is_deleted == False
    )
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        (
            await db.execute(
                query.order_by(
                    Deviation.discovery_date.desc().nullslast(),
                    Deviation.created_at.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [
        DeviationReportRecordListItem(
            id=str(item.id),
            deviation_id=item.id,
            deviation_code=item.deviation_code,
            report_time=item.discovery_date,
            description=item.description,
            report_document=item.report_content,
            product_batch=item.affected_items or item.batch_number,
            department=item.department,
            reporter_name=item.discoverer,
            report_status=item.status,
            feishu_base_table_id=item.feishu_base_table_id,
            feishu_base_record_id=item.feishu_base_record_id,
            feishu_sync_status=item.feishu_sync_status,
            feishu_last_sync_error=item.feishu_last_sync_error,
            feishu_last_sync_direction=item.feishu_last_sync_direction,
            feishu_synced_at=item.feishu_synced_at,
            feishu_source_updated_at=item.feishu_source_updated_at,
        ).model_dump()
        for item in rows
    ]
    return _build_page_result(items, total, page, page_size)

async def get_deviation_detail(db: AsyncSession, deviation_id: uuid.UUID) -> DeviationDetail:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")
    return DeviationDetail.model_validate(deviation)


async def get_related_capas_for_deviation(
    db: AsyncSession,
    deviation_id: uuid.UUID,
) -> list[dict]:
    """Return deduplicated CAPA list linked to a deviation.

    Uses repository.get_related_capas_for_deviation and removes duplicates by CAPA.id.
    """
    from app.modules.quality.repository import quality_management as repository
    from app.modules.quality.schemas.capa import CapaListItem

    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise ValueError("偏差不存在")

    capas = await repository.get_related_capas_for_deviation(
        db, deviation.id, deviation.deviation_code
    )
    unique: list[CAPA] = []
    seen: set[uuid.UUID] = set()
    for capa in capas:
        if capa.id in seen:
            continue
        seen.add(capa.id)
        unique.append(capa)
    return [CapaListItem.model_validate(capa).model_dump() for capa in unique]


@dataclass(slots=True)
class SelectedReporterContact:
    name: str | None
    open_id: str | None
    department: str | None = None


async def _resolve_selected_reporter_contact(
    db: AsyncSession, reporter_open_id: str | None
) -> SelectedReporterContact:
    normalized_open_id = (reporter_open_id or "").strip()
    if not normalized_open_id:
        raise ValueError("报告人不能为空")

    feishu_contact_result = await get_department_contact_list_from_feishu(
        db, page=1, page_size=1000
    )
    for contact in feishu_contact_result.get("items", []):
        if str(contact.get("open_id") or "").strip() == normalized_open_id:
            return SelectedReporterContact(
                name=contact.get("name"),
                open_id=contact.get("open_id"),
                department=contact.get("department"),
            )

    raise ValueError("所选报告人不存在于部门联系人台账中")


def _parse_optional_datetime(value: str | None) -> datetime | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return datetime.fromisoformat(normalized)


async def create_deviation(
    db: AsyncSession,
    data: CreateDeviationRequest,
    user_id: str,
    current_user: User | None = None,
) -> dict[str, str]:
    reporter_contact: SelectedReporterContact | None = None
    if (data.reporter_open_id or "").strip():
        reporter_contact = await _resolve_selected_reporter_contact(
            db, data.reporter_open_id
        )
    description = (data.description or "").strip()
    product_batch = (data.affected_items or "").strip()
    department = (data.department or "").strip()
    if not department and reporter_contact and reporter_contact.department:
        department = str(reporter_contact.department).strip()

    if not description:
        raise ValueError("偏差内容不能为空")
    if not product_batch:
        raise ValueError("涉及产品名称/批号不能为空")

    now = datetime.now(timezone.utc)
    investigation_completed_at = _parse_optional_datetime(
        data.investigation_completed_at
    )
    is_closed = bool(data.is_closed)
    close_time = _parse_optional_datetime(data.close_time)
    status = "closed" if is_closed else "draft"
    status_updated_at = (close_time or now) if is_closed else now
    deviation = Deviation(
        deviation_code=await _generate_monthly_deviation_code(db, now),
        title=(data.title or description)[:255],
        department=department,
        discovery_date=(
            datetime.fromisoformat(data.discovery_date)
            if data.discovery_date
            else now
        ),
        discovery_time=data.discovery_time,
        discovery_location=data.discovery_location,
        level=data.level,
        root_cause_category=data.root_cause_category,
        description=description,
        immediate_actions=data.immediate_actions,
        attachments=data.attachments,
        affected_items=product_batch,
        batch_number=data.batch_number,
        handler=data.handler,
        needs_cross_dept_review=data.needs_cross_dept_review,
        cross_dept_reviewers=[r.model_dump() for r in data.cross_dept_reviewers] if data.cross_dept_reviewers else [],
        reporter_id=None,
        discoverer=(
            reporter_contact.name
            if reporter_contact and reporter_contact.name
            else (current_user.name if current_user else "")
        ),
        has_occurred_before=data.has_occurred_before,
        material_disposition=data.material_disposition,
        corrective_actions=data.corrective_actions,
        root_cause_analysis=data.root_cause_analysis,
        investigation_completed_at=investigation_completed_at,
        status=status,
        status_updated_at=status_updated_at,
    )
    db.add(deviation)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    await db.flush()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_after_write(db, deviation.id)
    return {"id": str(deviation.id), "code": deviation.deviation_code}

async def update_deviation(db: AsyncSession, deviation_id: uuid.UUID, data: UpdateDeviationRequest, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    is_closed = update_data.pop("is_closed", None)
    close_time = update_data.pop("close_time", None)

    for field, value in update_data.items():
        if field in ["ai_analysis", "investigation_records", "review_opinions", "cross_dept_reviewers", "report_versions"]:
            setattr(deviation, field, value)
        elif field == "discovery_date" and value:
            setattr(deviation, field, datetime.fromisoformat(value))
        elif field == "investigation_completed_at" and value:
            setattr(deviation, field, datetime.fromisoformat(value))
        else:
            setattr(deviation, field, value)

    if "investigation_completed_at" in update_data and not update_data.get("investigation_completed_at"):
        deviation.investigation_completed_at = None

    if is_closed is not None:
        if is_closed:
            deviation.status = "closed"
            deviation.status_updated_at = (
                _parse_optional_datetime(close_time) or datetime.now(timezone.utc)
            )
        elif deviation.status == "closed":
            deviation.status = "draft"
            deviation.status_updated_at = datetime.now(timezone.utc)

    deviation.updated_at = datetime.now(timezone.utc)
    if data.status:
        deviation.status_updated_at = datetime.now(timezone.utc)

    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_after_write(db, deviation.id)
    return {"success": True}

async def delete_deviation(db: AsyncSession, deviation_id: uuid.UUID) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")
    deviation.is_deleted = True
    deviation.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

async def submit_investigation(db: AsyncSession, deviation_id: uuid.UUID, data: SubmitInvestigationRequest, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")
    if deviation.status != "pending_investigation":
        raise ValueError("只有待调查状态的偏差才能提交调查报告")

    if data.description:
        deviation.description = data.description
    if data.investigation_records:
        deviation.investigation_records = data.investigation_records

    deviation.status = "pending_dept_head_review"
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

async def submit_review(db: AsyncSession, deviation_id: uuid.UUID, data: SubmitReviewRequest, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")

    current_step = STATUS_TO_STEP.get(deviation.status)
    if not current_step:
        raise ValueError("当前状态不在审核流程中")
    if current_step != data.step:
        raise ValueError("当前需要完成的审核步骤与提交的不一致")

    review_opinions = deviation.review_opinions or []
    new_opinion = {
        "content": data.content,
        "author": user_id,
        "step": data.step,
        "result": data.result,
        "createTime": datetime.now(timezone.utc).isoformat(),
    }
    review_opinions.append(new_opinion)

    if data.result == "rejected":
        deviation.status = "returned"
        deviation.returned_step = data.step
        deviation.review_opinions = review_opinions
        deviation.status_updated_at = datetime.now(timezone.utc)
        deviation.updated_at = datetime.now(timezone.utc)
        try:

            await db.commit()

        except Exception:

            await db.rollback()

            raise
        return {"success": True}

    next_status = STEP_TO_NEXT_STATUS.get(data.step)
    if not next_status:
        raise ValueError("无法确定下一步状态")

    if data.step == "qa_review" and data.result == "approved" and data.reason_category:
        deviation.root_cause_category = data.reason_category
    if data.step == "qa_head_review" and data.deviation_level:
        deviation.level = data.deviation_level

    deviation.status = next_status
    deviation.review_opinions = review_opinions
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

async def submit_final_code(db: AsyncSession, deviation_id: uuid.UUID, final_code: str, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")
    if deviation.status != "pending_final_code":
        raise ValueError("当前状态不允许提交最终编号")
    if not final_code or not final_code.strip():
        raise ValueError("最终编号不能为空")

    deviation.final_code = final_code.strip()
    deviation.status = "closed"
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

async def resubmit_deviation(db: AsyncSession, deviation_id: uuid.UUID, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(Deviation).where(Deviation.id == deviation_id, Deviation.is_deleted == False))
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise ValueError(f"Deviation {deviation_id} not found")
    if deviation.status != "returned":
        raise ValueError("只有退回状态的偏差才能重新提交")

    returned_step = deviation.returned_step
    target_status = STATUS_TO_PENDING.get(returned_step, "pending_investigation") if returned_step else "pending_investigation"

    deviation.status = target_status
    deviation.returned_step = None
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

# ============ CAPA Service ============
async def get_change_list(
    db: AsyncSession,
    change_code: str | None = None,
    applicant_department: str | None = None,
    change_object: str | None = None,
    change_level: str | None = None,
    application_date_from: str | None = None,
    application_date_to: str | None = None,
    planned_approval_date_from: str | None = None,
    planned_approval_date_to: str | None = None,
    execution_date_from: str | None = None,
    execution_date_to: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    content_keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    items, total = await repository.get_changes(
        db,
        change_code=change_code,
        applicant_department=applicant_department,
        change_object=change_object,
        change_level=change_level,
        application_date_from=_parse_date_filter(application_date_from),
        application_date_to=_parse_date_filter(application_date_to),
        planned_approval_date_from=_parse_date_filter(planned_approval_date_from),
        planned_approval_date_to=_parse_date_filter(planned_approval_date_to),
        execution_date_from=_parse_date_filter(execution_date_from),
        execution_date_to=_parse_date_filter(execution_date_to),
        closure_date_from=_parse_date_filter(closure_date_from),
        closure_date_to=_parse_date_filter(closure_date_to),
        content_keyword=content_keyword,
        page=page,
        page_size=page_size,
    )

    return _build_page_result(
        await _build_change_list_items(db, items),
        total,
        page,
        page_size,
    )


async def get_change_detail(db: AsyncSession, change_id: uuid.UUID) -> ChangeDetail:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id, ChangeControl.is_deleted == False
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise ValueError(f"Change {change_id} not found")
    return ChangeDetail.model_validate(change)


async def create_change(
    db: AsyncSession, data: CreateChangeRequest, user_id: str
) -> dict[str, str]:
    change_code = (data.change_code or "").strip()
    if not change_code:
        change_code = await generate_next_change_code(db)
    elif await repository.quality_management.exists_by_change_code(db, change_code):
        raise ValueError("变更控制号已存在")

    change = ChangeControl(
        serial_number=data.serial_number,
        change_code=change_code,
        applicant_department=data.applicant_department,
        change_object=data.change_object,
        change_content=data.change_content,
        impact_assessment=data.impact_assessment,
        change_level=data.change_level,
        application_date=data.application_date,
        planned_approval_date=data.planned_approval_date,
        execution_date=data.execution_date,
        closure_date=data.closure_date,
    )
    db.add(change)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.flush()

    # Sync to Feishu Bitable (best-effort, non-blocking)
    try:
        from app.modules.quality.service import quality_feishu_pages
        await quality_feishu_pages.sync_change_to_feishu(db, change)
    except Exception:
        pass

    return {"id": str(change.id), "code": change.change_code}


async def update_change(
    db: AsyncSession, change_id: uuid.UUID, data: UpdateChangeRequest, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id, ChangeControl.is_deleted == False
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise ValueError(f"Change {change_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    next_change_code = update_data.get("change_code")
    if isinstance(next_change_code, str):
        next_change_code = next_change_code.strip()
        update_data["change_code"] = next_change_code
        if next_change_code and await repository.quality_management.exists_by_change_code(
            db, next_change_code, exclude_id=change.id
        ):
            raise ValueError("变更控制号已存在")
    for field, value in update_data.items():
        setattr(change, field, value)

    change.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # Sync to Feishu Bitable (best-effort, non-blocking)
    try:
        from app.modules.quality.service import quality_feishu_pages
        await quality_feishu_pages.sync_change_to_feishu(db, change)
    except Exception:
        pass

    return {"success": True}


async def delete_change(db: AsyncSession, change_id: uuid.UUID) -> dict[str, bool]:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id, ChangeControl.is_deleted == False
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise ValueError(f"Change {change_id} not found")

    change_code = change.change_code
    change.is_deleted = True
    change.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # Delete from Feishu Bitable (best-effort, non-blocking)
    try:
        from app.modules.quality.service import quality_feishu_pages
        await quality_feishu_pages.delete_change_from_feishu(db, change_code)
    except Exception:
        pass

    return {"success": True}


async def generate_next_change_code(db: AsyncSession) -> str:
    now = datetime.now()
    prefix = f"BG-{now:%y%m}"
    sequence_pattern = re.compile(rf"^{re.escape(prefix)}(\d{{3}})$")
    change_codes = await repository.quality_management.list_change_codes_by_prefix(
        db, prefix
    )

    max_sequence = 0
    for change_code in change_codes:
        matched = sequence_pattern.match(change_code)
        if matched:
            max_sequence = max(max_sequence, int(matched.group(1)))

    return f"{prefix}{max_sequence + 1:03d}"


async def get_capa_list(
    db: AsyncSession,
    status: str | None = None,
    source: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    capa_code: str | None = None,
    affected_product: str | None = None,
    source_code: str | None = None,
    evaluation_result: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    department: str | None = None,
    qa_confirmer: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    items, total = await repository.get_capas(
        db,
        status=status,
        source=source,
        category=category,
        keyword=keyword,
        capa_code=capa_code,
        affected_product=affected_product,
        source_code=source_code,
        evaluation_result=evaluation_result,
        closure_date_from=_parse_datetime_filter(closure_date_from),
        closure_date_to=_parse_datetime_filter_end_exclusive(closure_date_to),
        department=department,
        qa_confirmer=qa_confirmer,
        page=page,
        page_size=page_size,
    )

    return _build_page_result(
        await _build_capa_list_items(db, items),
        total,
        page,
        page_size,
    )

async def get_capa_detail(db: AsyncSession, capa_id: uuid.UUID) -> CapaDetail:
    result = await db.execute(select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted == False))
    capa = result.scalar_one_or_none()
    if not capa:
        raise ValueError(f"CAPA {capa_id} not found")
    return CapaDetail.model_validate(capa)

async def create_capa(db: AsyncSession, data: CreateCapaRequest, user_id: str) -> dict[str, str]:
    capa = CAPA(
        capa_code=f"CAPA-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        title=data.title,
        deviation_id=data.deviation_id,
        source=data.source,
        source_code=data.source_code,
        category=data.category,
        root_cause_category=data.root_cause_category,
        non_conformity_description=data.non_conformity_description,
        root_cause_analysis=data.root_cause_analysis,
        capa_content=data.capa_content,
        capa_items=[item.model_dump() for item in data.capa_items] if data.capa_items else [],
        executors=data.executors,
        expected_completion_date=datetime.fromisoformat(data.expected_completion_date) if data.expected_completion_date else None,
        reporter=data.reporter,
        status="draft",
        status_updated_at=datetime.now(timezone.utc),
    )
    db.add(capa)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    await db.flush()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_after_write(db, capa.id)
    return {"id": str(capa.id), "code": capa.capa_code}

async def update_capa(db: AsyncSession, capa_id: uuid.UUID, data: UpdateCapaRequest, user_id: str) -> dict[str, bool]:
    result = await db.execute(select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted == False))
    capa = result.scalar_one_or_none()
    if not capa:
        raise ValueError(f"CAPA {capa_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ["capa_items", "execution_tracks", "dept_head_confirmations", "report_versions"]:
            setattr(capa, field, value)
        elif field in ["expected_completion_date", "evaluation_deadline", "evaluation_confirm_date", "closure_date", "qa_review_time", "q_head_approval_time"] and value:
            setattr(capa, field, datetime.fromisoformat(value))
        else:
            setattr(capa, field, value)

    capa.updated_at = datetime.now(timezone.utc)
    if data.status:
        capa.status_updated_at = datetime.now(timezone.utc)

    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_after_write(db, capa.id)
    return {"success": True}

async def delete_capa(db: AsyncSession, capa_id: uuid.UUID) -> dict[str, bool]:
    result = await db.execute(select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted == False))
    capa = result.scalar_one_or_none()
    if not capa:
        raise ValueError(f"CAPA {capa_id} not found")
    capa.is_deleted = True
    capa.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

# ============ Department Contact Service ============
def _normalize_feishu_contact_value(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_normalize_feishu_contact_value(item) for item in value]
        normalized = [part for part in parts if part]
        return " / ".join(normalized) if normalized else None
    if isinstance(value, dict):
        for key in ("text", "name", "email", "link", "value"):
            if key in value:
                normalized = _normalize_feishu_contact_value(value[key])
                if normalized:
                    return normalized
        return None
    return str(value).strip() or None


def _format_feishu_contact_datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
    return ""


def _normalize_feishu_contact_person_id(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                person_id = str(item.get("id") or "").strip()
                if person_id:
                    return person_id
    if isinstance(value, dict):
        person_id = str(value.get("id") or "").strip()
        if person_id:
            return person_id
        nested_value = value.get("value")
        if isinstance(nested_value, list):
            for item in nested_value:
                if isinstance(item, dict):
                    person_id = str(item.get("id") or "").strip()
                    if person_id:
                        return person_id
    return None


def _serialize_feishu_department_contact(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", {})
    return {
        "id": record.get("record_id", ""),
        "name": _normalize_feishu_contact_value(fields.get("姓名 (人员 )")),
        "bitable_user_id": _normalize_feishu_contact_person_id(fields.get("姓名 (人员 )")),
        "department": _normalize_feishu_contact_value(fields.get("部门")) or "",
        "enterprise_email": _normalize_feishu_contact_value(fields.get("企业邮箱")),
        "open_id": _normalize_feishu_contact_value(fields.get("Open ID")),
        "department_head_name": _normalize_feishu_contact_value(
            fields.get("上级负责人姓名 (人员 )")
        ),
        "department_head_bitable_user_id": _normalize_feishu_contact_person_id(
            fields.get("上级负责人姓名 (人员 )")
        ),
        "department_head_enterprise_email": _normalize_feishu_contact_value(
            fields.get("部门负责人企业邮箱")
        ),
        "department_head_open_id": _normalize_feishu_contact_value(
            fields.get("部门负责人Open ID")
        ),
        "feishu_record_id": record.get("record_id"),
        "created_at": _format_feishu_contact_datetime(record.get("created_time")),
        "updated_at": _format_feishu_contact_datetime(record.get("last_modified_time")),
    }


async def get_department_contact_list(db: AsyncSession, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    query = select(DepartmentContact).where(DepartmentContact.is_deleted == False)
    count_query = select(func.count()).select_from(DepartmentContact).where(DepartmentContact.is_deleted == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        query.order_by(DepartmentContact.department, DepartmentContact.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            DepartmentContactOut.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_department_contact_list_from_feishu(
    db: AsyncSession,
    page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
    from app.platform.integrations.feishu.utils import build_bitable_client

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    entity = runtime.get_entity_config("department_contact", direction="pull")
    if not runtime.is_enabled() or not entity or not entity.app_token or not entity.table_id:
        raise ValueError("部门联系人飞书同步未启用或未完成配置")

    client = build_bitable_client(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    page_token: str | None = None
    records: list[dict[str, Any]] = []

    while True:
        params: dict[str, Any] = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = await client.client.request(
            "POST",
            client._path(entity.table_id, "/records/search"),
            json={
                "automatic_fields": True,
            },
            params=params,
        )
        records.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break

    serialized = [_serialize_feishu_department_contact(record) for record in records]
    serialized.sort(key=lambda item: (item["department"], item["name"] or ""))
    total = len(serialized)
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return {
        "items": serialized[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

async def _ensure_department_contact_open_id_unique(
    db: AsyncSession,
    open_id: str | None,
    *,
    exclude_contact_id: uuid.UUID | None = None,
) -> None:
    if not open_id:
        return
    conditions = [
        DepartmentContact.open_id == open_id,
        DepartmentContact.is_deleted == False,
    ]
    if exclude_contact_id is not None:
        conditions.append(DepartmentContact.id != exclude_contact_id)
    result = await db.execute(select(DepartmentContact).where(*conditions))
    if result.scalar_one_or_none():
        raise ValueError(f"DepartmentContact with open_id {open_id} already exists")


async def upsert_department_contact(
    db: AsyncSession,
    data: CreateDepartmentContactRequest | UpdateDepartmentContactRequest,
    department: str | None,
    user_id: str,
) -> dict[str, bool]:
    del department, user_id
    if not isinstance(data, CreateDepartmentContactRequest):
        raise ValueError("CreateDepartmentContactRequest required")
    await _ensure_department_contact_open_id_unique(db, data.open_id)

    contact = DepartmentContact(**data.model_dump())
    db.add(contact)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}


async def update_department_contact(
    db: AsyncSession,
    contact_id: uuid.UUID,
    data: UpdateDepartmentContactRequest,
) -> dict[str, bool]:
    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.id == contact_id,
            DepartmentContact.is_deleted == False,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise ValueError(f"DepartmentContact {contact_id} not found")

    update_data = data.model_dump(exclude_unset=True)
    await _ensure_department_contact_open_id_unique(
        db,
        update_data.get("open_id"),
        exclude_contact_id=contact_id,
    )
    for field, value in update_data.items():
        setattr(contact, field, value)
    contact.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}

async def delete_department_contact(db: AsyncSession, contact_id: uuid.UUID) -> dict[str, bool]:
    result = await db.execute(select(DepartmentContact).where(DepartmentContact.id == contact_id, DepartmentContact.is_deleted == False))
    contact = result.scalar_one_or_none()
    if not contact:
        raise ValueError(f"DepartmentContact {contact_id} not found")
    contact.is_deleted = True
    contact.updated_at = datetime.now(timezone.utc)
    try:

        await db.commit()

    except Exception:

        await db.rollback()

        raise
    return {"success": True}

# ============ Statistics ============
async def get_deviation_statistics(db: AsyncSession) -> DeviationStatistics:
    from app.modules.quality.service import quality_feishu_pages

    try:
        result = await quality_feishu_pages.list_deviation_ledger_records(
            db,
            page=1,
            page_size=99999,
        )
        items = result.get("items", [])
    except Exception:
        items = []

    total = len(items)
    pending = sum(1 for item in items if item.get("status") != "closed")
    closedCount = sum(1 for item in items if item.get("status") == "closed")

    department_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    root_cause_counts: dict[str, int] = {}

    for item in items:
        # Status
        status = item.get("status") or "draft"
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Level
        level = item.get("level") or "unknown"
        level_counts[level] = level_counts.get(level, 0) + 1
        
        # Department
        dept = item.get("department") or "未知"
        department_counts[dept] = department_counts.get(dept, 0) + 1
        
        # Root cause category
        rc = item.get("root_cause_category") or "unknown"
        root_cause_counts[rc] = root_cause_counts.get(rc, 0) + 1

    department_distribution = [{"name": k, "count": v} for k, v in department_counts.items()]
    status_distribution = [{"status": k, "count": v} for k, v in status_counts.items()]
    level_distribution = [{"level": k, "count": v} for k, v in level_counts.items()]
    root_cause_distribution = [{"category": k, "count": v} for k, v in root_cause_counts.items()]

    step_breakdown = []

    return DeviationStatistics(
        total=total,
        pending=pending,
        closedCount=closedCount,
        departmentDistribution=department_distribution,
        statusDistribution=status_distribution,
        levelDistribution=level_distribution,
        rootCauseDistribution=root_cause_distribution,
        stepBreakdown=step_breakdown,
    )

async def get_capa_statistics(db: AsyncSession) -> CapaStatistics:
    from app.modules.quality.service import feishu_capa

    try:
        result = await feishu_capa.list_capa_ledger(
            db,
            page=1,
            page_size=99999,
        )
        items = result.get("items", [])
    except Exception:
        items = []

    total = len(items)
    closedCount = sum(1 for item in items if item.get("status") == "closed")
    
    # Simple overdue count for demonstration (would need proper date parsing)
    today_str = date.today().isoformat()
    overdueCount = 0
    for item in items:
        if item.get("status") not in ("closed", "cancelled"):
            exp_date = item.get("expected_completion_date")
            if exp_date and str(exp_date) < today_str:
                overdueCount += 1

    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    department_counts: dict[str, int] = {}

    for item in items:
        status = item.get("status") or "draft"
        status_counts[status] = status_counts.get(status, 0) + 1
        
        source = item.get("source") or "未知"
        source_counts[source] = source_counts.get(source, 0) + 1
        
        category = item.get("category") or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
        
        dept = item.get("department") or item.get("事件部门") or "未知"
        department_counts[dept] = department_counts.get(dept, 0) + 1

    status_distribution = [{"status": k, "count": v} for k, v in status_counts.items()]
    source_distribution = [{"source": k, "count": v} for k, v in source_counts.items()]
    category_distribution = [{"category": k, "count": v} for k, v in category_counts.items()]
    department_distribution = [{"name": k, "count": v} for k, v in department_counts.items()]

    return CapaStatistics(
        total=total,
        closedCount=closedCount,
        overdueCount=overdueCount,
        statusDistribution=status_distribution,
        sourceDistribution=source_distribution,
        categoryDistribution=category_distribution,
        departmentDistribution=department_distribution,
    )


async def get_change_statistics(db: AsyncSession) -> ChangeStatistics:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
    from app.platform.integrations.feishu.utils import build_bitable_client

    def _get_change_field(
        entity: Any,
        fields: dict[str, Any],
        *system_fields: str,
    ) -> Any:
        for system_field in system_fields:
            try:
                mapped_value = feishu_sync_service._get_mapped_field_value(
                    entity, fields, system_field
                )
            except Exception:
                mapped_value = None
            if mapped_value not in (None, "", []):
                return mapped_value
            raw_value = fields.get(system_field)
            if raw_value not in (None, "", []):
                return raw_value
        return None

    def _parse_change_date(value: Any) -> date | None:
        parsed = feishu_sync_service._parse_feishu_datetime(value)
        return parsed.date() if parsed else None

    def _normalize_change_status(
        raw_status: str | None,
        execution_date: date | None,
        closure_date: date | None,
    ) -> str:
        normalized = (raw_status or "").strip().lower()
        if closure_date or normalized in {
            "closed",
            "completed",
            "done",
            "finished",
            "已关闭",
            "已完成",
            "完成",
            "关闭",
        }:
            return "closed"
        if execution_date or normalized in {
            "executing",
            "in_progress",
            "processing",
            "running",
            "执行中",
            "实施中",
            "进行中",
        }:
            return "in_progress"
        if normalized in {
            "approved",
            "pending_approval",
            "pending",
            "draft",
            "submitted",
            "待审批",
            "待审核",
            "草稿",
            "新建",
            "已提交",
        }:
            return "pending"
        return "pending"

    def _is_meaningful_dimension(value: str | None) -> bool:
        return bool(value and value.strip() and value.strip().lower() not in {"unknown", "未知", "n/a", "null"})

    try:
        runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
        entity = runtime.get_entity_config("change_ledger", direction="pull")
        if not runtime.is_enabled() or not entity or not entity.app_token or not entity.table_id:
            items = []
        else:
            client = build_bitable_client(
                app_token=entity.app_token,
                app_id=runtime.app_id,
                app_secret=runtime.app_secret,
            )
            records = await client.search_records(entity.table_id, automatic_fields=True, page_size=9999)
            items = []
            normalize_text = feishu_sync_service._normalize_text
            for r in records:
                fields = r.get("fields") or {}
                raw_status = normalize_text(
                    _get_change_field(entity, fields, "变更状态", "状态")
                )
                level = normalize_text(
                    _get_change_field(entity, fields, "变更等级", "变更级别")
                )
                change_type = normalize_text(
                    _get_change_field(entity, fields, "变更类型")
                )
                department = normalize_text(
                    _get_change_field(entity, fields, "变更申请部门", "申请部门", "部门")
                )
                application_date = _parse_change_date(
                    _get_change_field(entity, fields, "变更申请日期", "申请日期")
                )
                planned_approval_date = _parse_change_date(
                    _get_change_field(entity, fields, "变更计划批准日期", "计划批准日期")
                )
                execution_date = _parse_change_date(
                    _get_change_field(entity, fields, "变更正式执行日期", "执行日期")
                )
                closure_date = _parse_change_date(
                    _get_change_field(entity, fields, "变更关闭日期", "关闭日期")
                )
                is_delayed = feishu_sync_service._normalize_bool_from_yes_no(
                    _get_change_field(entity, fields, "是否延期")
                )
                if is_delayed is None:
                    compare_date = closure_date or execution_date
                    is_delayed = bool(
                        planned_approval_date
                        and compare_date
                        and compare_date > planned_approval_date
                    )

                items.append({
                    "status": _normalize_change_status(
                        raw_status,
                        execution_date=execution_date,
                        closure_date=closure_date,
                    ),
                    "raw_status": raw_status,
                    "level": level,
                    "type": change_type,
                    "department": department,
                    "application_date": application_date,
                    "planned_approval_date": planned_approval_date,
                    "execution_date": execution_date,
                    "closure_date": closure_date,
                    "is_delayed": is_delayed,
                })
    except Exception:
        items = []

    total = len(items)
    closedCount = sum(1 for item in items if item.get("status") == "closed")
    delayCount = sum(1 for item in items if item.get("is_delayed"))
    inProgressCount = sum(1 for item in items if item.get("status") == "in_progress")

    status_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    department_counts: dict[str, int] = {}

    for item in items:
        status = item.get("status") or "draft"
        status_counts[status] = status_counts.get(status, 0) + 1

        level = item.get("level")
        if _is_meaningful_dimension(level):
            level_counts[level] = level_counts.get(level, 0) + 1

        ctype = item.get("type")
        if _is_meaningful_dimension(ctype):
            type_counts[ctype] = type_counts.get(ctype, 0) + 1

        dept = item.get("department")
        if _is_meaningful_dimension(dept):
            department_counts[dept] = department_counts.get(dept, 0) + 1

    status_distribution = [{"status": k, "count": v} for k, v in status_counts.items()]
    level_distribution = [{"level": k, "count": v} for k, v in level_counts.items()]
    type_distribution = [{"type": k, "count": v} for k, v in type_counts.items()]
    department_distribution = [{"name": k, "count": v} for k, v in department_counts.items()]

    action_plan_total = closedCount + inProgressCount
    action_plan_overdue = delayCount
    action_plan_confirmed = closedCount

    return ChangeStatistics(
        total=total,
        closedCount=closedCount,
        delayCount=delayCount,
        statusDistribution=status_distribution,
        levelDistribution=level_distribution,
        typeDistribution=type_distribution,
        departmentDistribution=department_distribution,
        actionPlanTotal=action_plan_total,
        actionPlanOverdue=action_plan_overdue,
        actionPlanConfirmed=action_plan_confirmed,
    )

# ============ Attachment Reviews ============
async def list_attachment_reviews(
    db: AsyncSession,
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
) -> list[dict]:
    """List attachment reviews with optional filters."""
    query = select(AttachmentReview).where(AttachmentReview.is_deleted == False)
    if deviation_id:
        query = query.where(AttachmentReview.deviation_id == deviation_id)
    if capa_id:
        query = query.where(AttachmentReview.capa_id == capa_id)
    if attachment_url:
        query = query.where(AttachmentReview.attachment_url == attachment_url)
    query = query.order_by(AttachmentReview.review_time.desc())
    
    result = await db.execute(query)
    items = result.scalars().all()
    return [AttachmentReviewOut.model_validate(item).model_dump() for item in items]

async def create_attachment_review(
    db: AsyncSession,
    data,
    reviewer_id: str,
) -> dict:
    """Create a new attachment review."""
    review = AttachmentReview(
        deviation_id=data.deviation_id,
        capa_id=data.capa_id,
        attachment_url=data.attachment_url,
        content=data.content,
        reviewer_id=reviewer_id,
        review_time=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.flush()
    await db.flush()
    return AttachmentReviewOut.model_validate(review).model_dump()

async def delete_attachment_review(db: AsyncSession, review_id: uuid.UUID) -> None:
    """Soft-delete an attachment review."""
    review = await db.get(AttachmentReview, review_id)
    if not review:
        raise ValueError("Attachment review not found")
    review.is_deleted = True
    await db.flush()


# ============ NEW: Deviation Workflow Endpoints ============

async def submit_for_review(db: AsyncSession, deviation_id: uuid.UUID, user_id: str) -> dict[str, bool]:
    """Submit deviation to start review workflow. draft → pending_ai_analysis."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise ValueError("偏差不存在")
    if deviation.status != "draft":
        raise ValueError(f"只有草稿状态的偏差可以提交，当前状态: {deviation.status}")

    deviation.status = "pending_ai_analysis"
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()

    # Trigger AI analysis asynchronously
    import asyncio
    asyncio.create_task(_trigger_ai_analysis(deviation_id, user_id))

    return {"success": True}


async def _trigger_ai_analysis(deviation_id: uuid.UUID, user_id: str):
    """Async trigger AI analysis for a deviation."""
    from app.modules.quality.service.ai_analysis import analyze_deviation_async
    try:
        await analyze_deviation_async(deviation_id, user_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"AI analysis failed for deviation {deviation_id}: {e}")


async def complete_ai_analysis(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    ai_analysis: dict | None,
    user_id: str,
) -> dict[str, bool]:
    """Mark AI analysis complete and advance to pending_investigation."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise ValueError("偏差不存在")
    if deviation.status != "pending_ai_analysis":
        raise ValueError(f"只有待AI分析状态的偏差才能完成AI分析，当前状态: {deviation.status}")

    if ai_analysis is not None:
        deviation.ai_analysis = ai_analysis
    deviation.status = "pending_investigation"
    deviation.status_updated_at = datetime.now(timezone.utc)
    deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def batch_update_status(
    db: AsyncSession,
    deviation_ids: list[uuid.UUID],
    target_status: str,
    user_id: str,
) -> dict:
    """Batch update status for multiple deviations."""
    updated = 0
    failures = []

    for did in deviation_ids:
        try:
            deviation = await db.get(Deviation, did)
            if not deviation or deviation.is_deleted:
                failures.append({"id": str(did), "reason": "偏差不存在"})
                continue

            deviation.status = target_status
            deviation.status_updated_at = datetime.now(timezone.utc)
            deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
            updated += 1
        except Exception as e:
            failures.append({"id": str(did), "reason": str(e)})

    await db.flush()
    return {"updated_count": updated, "failed_count": len(failures), "failures": failures}


async def get_department_confirmations(
    db: AsyncSession,
    week_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List department weekly confirmations."""
    query = select(DepartmentWeeklyConfirmation).where(
        DepartmentWeeklyConfirmation.is_deleted == False
    )
    if week_key:
        query = query.where(DepartmentWeeklyConfirmation.week_key == week_key)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(DepartmentWeeklyConfirmation.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [DepartmentWeeklyConfirmationOut.model_validate(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def confirm_production_status(
    db: AsyncSession,
    data,
    user_id: str,
) -> dict[str, bool]:
    """Create or update a department weekly confirmation."""
    query = select(DepartmentWeeklyConfirmation).where(
        DepartmentWeeklyConfirmation.department == data.department,
        DepartmentWeeklyConfirmation.week_key == data.week_key,
        DepartmentWeeklyConfirmation.is_deleted == False,
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.production_status = data.production_status
        existing.deviation_status = data.deviation_status
        existing.confirmed_by_id = uuid.UUID(user_id) if user_id != "system" else None
        existing.confirmed_at = now
        existing.updated_at = now
    else:
        confirmation = DepartmentWeeklyConfirmation(
            department=data.department,
            week_key=data.week_key,
            production_status=data.production_status,
            deviation_status=data.deviation_status,
            confirmed_by_id=uuid.UUID(user_id) if user_id != "system" else None,
            confirmed_at=now,
        )
        db.add(confirmation)

    await db.flush()
    return {"success": True}


async def get_stopped_departments(db: AsyncSession, week_key: str) -> list[str]:
    """Get departments with stopped production status for a given week."""
    query = select(DepartmentWeeklyConfirmation.department).where(
        DepartmentWeeklyConfirmation.week_key == week_key,
        DepartmentWeeklyConfirmation.production_status == "stopped",
        DepartmentWeeklyConfirmation.is_deleted == False,
    )
    result = await db.execute(query)
    return [row[0] for row in result.all()]


# ============ NEW: CAPA Workflow Endpoints ============

async def get_capa_departments(db: AsyncSession) -> list[str]:
    """Get all departments from department contacts."""
    query = select(DepartmentContact.department).where(
        DepartmentContact.is_deleted == False
    )
    result = await db.execute(query)
    return [row[0] for row in result.all()]


async def auto_fill_from_deviation(db: AsyncSession, deviation_id: uuid.UUID) -> dict:
    """Auto-fill CAPA form from deviation data."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise ValueError("偏差不存在")

    # Extract from AI analysis
    ai_analysis = deviation.ai_analysis or {}
    non_conformity = ai_analysis.get("structured_deviation_description", deviation.description or "")
    root_cause = ai_analysis.get("preliminary_cause_analysis", "")

    # Extract from last investigation record
    investigation_records = deviation.investigation_records or []
    capa_content = ""
    if investigation_records:
        last_record = investigation_records[-1] if isinstance(investigation_records, list) else {}
        if isinstance(last_record, dict):
            non_conformity = last_record.get("nonconformityDescription", non_conformity)
            root_cause = last_record.get("rootCauseAnalysis", root_cause)
            # Build capa content from proposals
            proposals = last_record.get("capaProposals", [])
            if proposals:
                capa_content = "\n".join(
                    f"{i+1}. {p.get('summary', p.get('content', ''))}"
                    for i, p in enumerate(proposals)
                )

    capa_suggestion = ai_analysis.get("capa_suggestions", "")
    if not capa_content and capa_suggestion:
        capa_content = capa_suggestion

    return {
        "title": deviation.title,
        "non_conformity_description": non_conformity,
        "root_cause_analysis": root_cause,
        "capa_content": capa_content,
        "expected_completion_date": None,
    }


async def link_deviation(
    db: AsyncSession,
    capa_id: uuid.UUID,
    deviation_id: uuid.UUID,
    user_id: str,
) -> dict[str, bool]:
    """Link a CAPA to a deviation."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise ValueError("偏差不存在")

    capa.deviation_id = deviation_id
    capa.source_code = deviation.deviation_code
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def complete_part(
    db: AsyncSession,
    capa_id: uuid.UUID,
    part: str,
    user_id: str,
) -> dict[str, bool]:
    """Mark CAPA part A or B as complete."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")

    # Store completion in capa_items or a tracking field
    # For simplicity, update status when both parts are complete
    items = capa.capa_items or []
    if part == "a":
        # Part A = problem description complete
        pass
    elif part == "b":
        # Part B = measures complete
        pass

    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def submit_capa(db: AsyncSession, capa_id: uuid.UUID, user_id: str) -> dict[str, bool]:
    """Submit CAPA for QA approval."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")
    if capa.status not in ("draft",):
        raise ValueError(f"只有草稿状态的CAPA可以提交，当前状态: {capa.status}")

    capa.status = "submitted"
    capa.status_updated_at = datetime.now(timezone.utc)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def confirm_dept_head(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data,
    user_id: str,
) -> dict[str, bool]:
    """Department head confirmation for CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")

    confirmations = capa.dept_head_confirmations or []
    now = datetime.now(timezone.utc).isoformat()

    confirmation = {
        "department": data.department,
        "deptHeadUserId": data.dept_head_user_id,
        "result": data.result,
        "opinion": data.opinion,
        "confirmTime": now,
    }

    # Update existing or append
    found = False
    for i, c in enumerate(confirmations):
        if isinstance(c, dict) and c.get("department") == data.department:
            confirmations[i] = confirmation
            found = True
            break
    if not found:
        confirmations.append(confirmation)

    capa.dept_head_confirmations = confirmations

    # Check if all departments have approved
    all_approved = all(
        isinstance(c, dict) and c.get("result") == "approved"
        for c in confirmations
    )
    any_rejected = any(
        isinstance(c, dict) and c.get("result") == "rejected"
        for c in confirmations
    )

    if all_approved and confirmations:
        capa.status = "pending_qa_approval"
        capa.status_updated_at = datetime.now(timezone.utc)
    elif any_rejected:
        capa.status = "returned"
        capa.returned_step = "dept_head_confirm"
        capa.status_updated_at = datetime.now(timezone.utc)

    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def approve_capa(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data,
    user_id: str,
) -> dict[str, bool]:
    """QA approval for CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")

    now = datetime.now(timezone.utc)

    if data.step == "qa_review":
        capa.qa_reviewer_id = uuid.UUID(user_id) if user_id != "system" else None
        capa.qa_review_opinion = data.opinion
        capa.qa_review_time = now
        if data.result == "approved":
            capa.status = "pending_q_head_approval"
        else:
            capa.status = "returned"
            capa.returned_step = "qa_review"

    elif data.step == "q_head_approval":
        capa.q_head_approver_id = uuid.UUID(user_id) if user_id != "system" else None
        capa.q_head_approval_opinion = data.opinion
        capa.q_head_approval_time = now
        if data.result == "approved":
            capa.status = "executing"
        else:
            capa.status = "returned"
            capa.returned_step = "q_head_approval"

    capa.status_updated_at = now
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def resubmit_capa(db: AsyncSession, capa_id: uuid.UUID, user_id: str) -> dict[str, bool]:
    """Resubmit CAPA after rejection."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")
    if capa.status != "returned":
        raise ValueError(f"只有已退回状态的CAPA可以重新提交，当前状态: {capa.status}")

    capa.status = "draft"
    capa.returned_step = None
    capa.status_updated_at = datetime.now(timezone.utc)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def add_execution_track(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data: dict,
    user_id: str,
) -> dict[str, bool]:
    """Add an execution tracking record to CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")

    tracks = capa.execution_tracks or []
    track = {
        "execution_status": data.get("execution_status", ""),
        "qa_confirmer": data.get("qa_confirmer", ""),
        "qa_confirm_date": data.get("qa_confirm_date", ""),
    }
    tracks.append(track)
    capa.execution_tracks = tracks
    capa.execution_status = data.get("execution_status", "")
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def delete_execution_track(
    db: AsyncSession,
    capa_id: uuid.UUID,
    index: int,
    user_id: str,
) -> dict[str, bool]:
    """Delete an execution tracking record by index."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")

    tracks = capa.execution_tracks or []
    if index < 0 or index >= len(tracks):
        raise ValueError("执行记录索引无效")

    tracks.pop(index)
    capa.execution_tracks = tracks
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def confirm_execution(db: AsyncSession, capa_id: uuid.UUID, user_id: str) -> dict[str, bool]:
    """Confirm CAPA execution is complete, advance to pending_evaluation."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")
    if capa.status != "executing":
        raise ValueError(f"只有执行中状态的CAPA可以确认执行完成，当前状态: {capa.status}")

    capa.status = "pending_evaluation"
    capa.status_updated_at = datetime.now(timezone.utc)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def submit_evaluation(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data,
    user_id: str,
) -> dict[str, bool]:
    """Submit effectiveness evaluation and close CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise ValueError("CAPA不存在")
    if capa.status != "pending_evaluation":
        raise ValueError(f"只有待效果评价状态的CAPA可以提交评价，当前状态: {capa.status}")

    capa.evaluation_target = data.evaluation_target
    capa.evaluation_result = data.evaluation_result
    capa.evaluation_confirmer_id = uuid.UUID(data.evaluation_confirmer) if data.evaluation_confirmer else None
    capa.evaluation_confirm_date = datetime.fromisoformat(data.evaluation_confirm_date.replace("Z", "+00:00")) if data.evaluation_confirm_date else None
    capa.closure_date = datetime.fromisoformat(data.closure_date.replace("Z", "+00:00")) if data.closure_date else None
    capa.status = "closed"
    capa.status_updated_at = datetime.now(timezone.utc)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}
