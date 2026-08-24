"""偏差（Deviation）业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality import repository
from app.modules.quality.models import (
    CAPA,
    DepartmentWeeklyConfirmation,
    Deviation,
)
from app.modules.quality.schemas import (
    CreateDeviationRequest,
    DepartmentWeeklyConfirmationOut,
    DeviationDetail,
    DeviationListItem,
    DeviationReportRecordListItem,
    SubmitInvestigationRequest,
    SubmitReviewRequest,
    UpdateDeviationRequest,
)
from app.modules.quality.service.department_contacts import (
    get_department_contact_list_from_feishu,
)
from app.modules.quality.service.quality_common import (
    _build_page_result,
    _parse_datetime_filter,
    _parse_datetime_filter_end_exclusive,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import User

logger = logging.getLogger(__name__)
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
    report_entity = runtime.get_entity_config(
        "deviation_report_record", direction="pull"
    )
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
        normalize_text(
            field_value(report_entity, record.get("fields") or {}, "偏差编号")
        )
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
        linked_deviation = deviation_map.get(deviation_code) if deviation_code else None
        item = DeviationReportRecordListItem(
            id=record.get("record_id", ""),
            deviation_id=linked_deviation.id if linked_deviation else None,
            deviation_code=deviation_code,
            report_time=parse_datetime(field_value(report_entity, fields, "报告时间")),
            description=normalize_text(field_value(report_entity, fields, "偏差内容")),
            report_document=normalize_text(
                field_value(report_entity, fields, "偏差报告")
            ),
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
            qa_head_name=normalize_text(field_value(report_entity, fields, "QA负责人")),
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
        item["reporters"] = feishu_sync_service._parse_person_field(
            field_value(report_entity, fields, "报告人")
        )
        item["department_heads"] = feishu_sync_service._parse_person_field(
            field_value(report_entity, fields, "部门负责人")
        )
        item["qas"] = feishu_sync_service._parse_person_field(
            field_value(report_entity, fields, "QA")
        )
        item["qa_heads"] = feishu_sync_service._parse_person_field(
            field_value(report_entity, fields, "QA负责人")
        )
        item["attachments"] = feishu_sync_service._parse_attachment_field(
            field_value(report_entity, fields, "附件")
        )
        item["report_status"] = _pick_report_status(item)
        items.append(item)

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


async def _get_deviation_report_record_from_feishu(
    db: AsyncSession,
    feishu_record_id: str,
) -> tuple[dict[str, Any], Any, Any]:
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
    report_entity = runtime.get_entity_config(
        "deviation_report_record", direction="pull"
    )
    if not runtime.is_enabled() or not report_entity:
        raise AppException(message="报告记录飞书 Base 未启用")

    records = await feishu_sync_service.feishu_sync.search_records(
        db,
        "deviation_report_record",
        None,
    )
    for record in records:
        if str(record.get("record_id") or "") == feishu_record_id:
            return record, report_entity, feishu_sync_service
    raise NotFoundException(resource="偏差报告记录")


async def ensure_deviation_from_report_record(
    db: AsyncSession,
    feishu_record_id: str,
) -> dict[str, Any]:
    (
        record,
        report_entity,
        feishu_sync_service,
    ) = await _get_deviation_report_record_from_feishu(
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
        raise AppException(message="飞书报告记录缺少偏差编号")

    description = normalize_text(field_value(report_entity, fields, "偏差内容"))
    report_content = normalize_text(field_value(report_entity, fields, "偏差报告"))
    product_batch = normalize_text(
        field_value(report_entity, fields, "涉及产品名称/批号")
    )
    department = normalize_text(field_value(report_entity, fields, "部门"))
    reporter_name = normalize_text(field_value(report_entity, fields, "报告人"))
    report_time = parse_datetime(field_value(report_entity, fields, "报告时间"))
    source_updated_at = get_record_modified_at(record)

    result = await db.execute(
        select(Deviation).where(
            Deviation.feishu_base_record_id == feishu_record_id,
            Deviation.is_deleted.is_(False),
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
    report_entity = runtime.get_entity_config(
        "deviation_report_record", direction="pull"
    )
    if not runtime.is_enabled() or not report_entity:
        raise AppException(message="无法从飞书报告记录表生成偏差编号")

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
    except Exception:  # pragma: no cover - guarded by tests below
        raise AppException(message="无法从飞书报告记录表生成偏差编号")

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
    scope: DepartmentScope | None = None,
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
        scope=scope,
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
    return await _build_deviation_report_record_items_from_feishu(
        db,
        page=page,
        page_size=page_size,
    )


async def get_deviation_detail(
    db: AsyncSession, deviation_id: uuid.UUID
) -> DeviationDetail:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
    return DeviationDetail.model_validate(deviation)


async def get_related_capas_for_deviation(
    db: AsyncSession,
    deviation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Return deduplicated CAPA list linked to a deviation.

    Uses repository.get_related_capas_for_deviation and removes duplicates by CAPA.id.
    """
    from app.modules.quality.repository import quality_management as repository
    from app.modules.quality.schemas.capa import CapaListItem

    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise NotFoundException(resource="偏差")

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
        raise AppException(message="报告人不能为空")

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

    raise AppException(message="所选报告人不存在于部门联系人台账中")


async def create_deviation(
    db: AsyncSession,
    data: CreateDeviationRequest,
    user_id: str,
    current_user: User | None = None,
) -> dict[str, str]:
    reporter_contact = await _resolve_selected_reporter_contact(
        db, data.reporter_open_id
    )
    description = (data.description or "").strip()
    product_batch = (data.affected_items or "").strip()
    department = (data.department or "").strip()

    if not department:
        raise AppException(message="部门不能为空")
    if not description:
        raise AppException(message="偏差内容不能为空")
    if not product_batch:
        raise AppException(message="涉及产品名称/批号不能为空")

    now = datetime.now(UTC)
    deviation = Deviation(
        deviation_code=await _generate_monthly_deviation_code(db, now),
        title=(data.title or description)[:255],
        department=department,
        discovery_date=(
            datetime.fromisoformat(data.discovery_date) if data.discovery_date else now
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
        has_occurred_before=data.has_occurred_before,
        previous_occurrence_code=data.previous_occurrence_code,
        material_disposition=data.material_disposition,
        corrective_actions=data.corrective_actions,
        root_cause_analysis=data.root_cause_analysis,
        investigation_completed_at=(
            datetime.fromisoformat(data.investigation_completed_at)
            if data.investigation_completed_at
            else None
        ),
        handler=data.handler,
        needs_cross_dept_review=data.needs_cross_dept_review,
        cross_dept_reviewers=[r.model_dump() for r in data.cross_dept_reviewers]
        if data.cross_dept_reviewers
        else [],
        reporter_id=None,
        discoverer=reporter_contact.name or "",
        status="draft",
        status_updated_at=now,
    )
    db.add(deviation)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    result = await db.execute(select(Deviation).where(Deviation.id == deviation.id))
    deviation = result.scalar_one()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_after_write(db, deviation.id)
    return {"id": str(deviation.id), "code": deviation.deviation_code}


async def update_deviation(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    data: UpdateDeviationRequest,
    user_id: str,
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))

    update_data = data.model_dump(exclude_unset=True)
    # 日期字段：前端传 ISO 字符串，需转换为 datetime，否则 SQLAlchemy 类型绑定失败
    date_fields = ["discovery_date", "investigation_completed_at", "close_time"]
    for field, value in update_data.items():
        if field in [
            "ai_analysis",
            "investigation_records",
            "review_opinions",
            "cross_dept_reviewers",
            "report_versions",
        ]:
            setattr(deviation, field, value)
        elif field in date_fields and value:
            setattr(
                deviation,
                field,
                datetime.fromisoformat(str(value).replace("Z", "+00:00")),
            )
        else:
            setattr(deviation, field, value)

    deviation.updated_at = datetime.now(UTC)
    if data.status:
        deviation.status_updated_at = datetime.now(UTC)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_deviation_after_write(db, deviation.id)
    return {"success": True}


async def delete_deviation(
    db: AsyncSession, deviation_id: uuid.UUID, deleted_by: uuid.UUID | None = None
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
    deviation.is_deleted = True
    deviation.deleted_by = deleted_by
    deviation.deleted_at = datetime.now(UTC)
    deviation.updated_at = datetime.now(UTC)
    await record_audit_log(
        db,
        action="delete",
        user_id=deleted_by,
        resource_type="quality.deviation",
        resource_id=deviation.id,
        old_value={
            "deviation_code": deviation.deviation_code,
            "title": deviation.title,
            "status": deviation.status,
        },
    )
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


async def submit_investigation(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    data: SubmitInvestigationRequest,
    user_id: str,
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
    if deviation.status != "pending_investigation":
        raise AppException(message="只有待调查状态的偏差才能提交调查报告")

    if data.description:
        deviation.description = data.description
    if data.investigation_records:
        deviation.investigation_records = data.investigation_records

    deviation.status = "pending_dept_head_review"
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_at = datetime.now(UTC)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


async def submit_review(
    db: AsyncSession, deviation_id: uuid.UUID, data: SubmitReviewRequest, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))

    current_step = STATUS_TO_STEP.get(deviation.status)
    if not current_step:
        raise AppException(message="当前状态不在审核流程中")
    if current_step != data.step:
        raise AppException(message="当前需要完成的审核步骤与提交的不一致")

    review_opinions = deviation.review_opinions or []
    new_opinion = {
        "content": data.content,
        "author": user_id,
        "step": data.step,
        "result": data.result,
        "createTime": datetime.now(UTC).isoformat(),
    }
    review_opinions.append(new_opinion)

    if data.result == "rejected":
        deviation.status = "returned"
        deviation.returned_step = data.step
        deviation.review_opinions = review_opinions
        deviation.status_updated_at = datetime.now(UTC)
        deviation.updated_at = datetime.now(UTC)
        try:
            await db.commit()

        except Exception:
            await db.rollback()

            raise
        return {"success": True}

    next_status = STEP_TO_NEXT_STATUS.get(data.step)
    if not next_status:
        raise AppException(message="无法确定下一步状态")

    if data.step == "qa_review" and data.result == "approved" and data.reason_category:
        deviation.root_cause_category = data.reason_category
    if data.step == "qa_head_review" and data.deviation_level:
        deviation.level = data.deviation_level

    deviation.status = next_status
    deviation.review_opinions = review_opinions
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_at = datetime.now(UTC)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


async def submit_final_code(
    db: AsyncSession, deviation_id: uuid.UUID, final_code: str, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
    if deviation.status != "pending_final_code":
        raise AppException(message="当前状态不允许提交最终编号")
    if not final_code or not final_code.strip():
        raise AppException(message="最终编号不能为空")

    deviation.final_code = final_code.strip()
    deviation.status = "closed"
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_at = datetime.now(UTC)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


async def resubmit_deviation(
    db: AsyncSession, deviation_id: uuid.UUID, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id, Deviation.is_deleted.is_(False)
        )
    )
    deviation = result.scalar_one_or_none()
    if not deviation:
        raise NotFoundException(resource="偏差", resource_id=str(deviation_id))
    if deviation.status != "returned":
        raise AppException(message="只有退回状态的偏差才能重新提交")

    returned_step = deviation.returned_step
    target_status = (
        STATUS_TO_PENDING.get(returned_step, "pending_investigation")
        if returned_step
        else "pending_investigation"
    )

    deviation.status = target_status
    deviation.returned_step = None
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_at = datetime.now(UTC)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


# ============ NEW: Deviation Workflow Endpoints ============


async def submit_for_review(
    db: AsyncSession, deviation_id: uuid.UUID, user_id: str
) -> dict[str, bool]:
    """Submit deviation to start review workflow. draft → pending_ai_analysis."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise NotFoundException(resource="偏差")
    if deviation.status != "draft":
        raise AppException(
            message=f"只有草稿状态的偏差可以提交，当前状态: {deviation.status}"
        )

    deviation.status = "pending_ai_analysis"
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()

    # 同步触发 AI 分析（避免 asyncio.create_task 导致任务重启丢失）
    # TODO: 后续接入 app/core/jobs.py 任务队列后改为异步任务
    await _trigger_ai_analysis(deviation_id, user_id)

    return {"success": True}


async def _trigger_ai_analysis(deviation_id: uuid.UUID, user_id: str) -> Any:
    """Async trigger AI analysis for a deviation."""
    from app.modules.quality.service.ai_analysis import analyze_deviation_async

    try:
        await analyze_deviation_async(deviation_id, user_id)
    except Exception:
        logger.exception("AI analysis failed for deviation %s", deviation_id)


async def complete_ai_analysis(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    ai_analysis: dict[str, Any] | None,
    user_id: str,
) -> dict[str, bool]:
    """Mark AI analysis complete and advance to pending_investigation."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise NotFoundException(resource="偏差")
    if deviation.status != "pending_ai_analysis":
        raise AppException(
            message=(
                f"只有待AI分析状态的偏差才能完成AI分析，当前状态: {deviation.status}"
            )
        )

    if ai_analysis is not None:
        deviation.ai_analysis = ai_analysis
    deviation.status = "pending_investigation"
    deviation.status_updated_at = datetime.now(UTC)
    deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def batch_update_status(
    db: AsyncSession,
    deviation_ids: list[uuid.UUID],
    target_status: str,
    user_id: str,
) -> dict[str, Any]:
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
            deviation.status_updated_at = datetime.now(UTC)
            deviation.updated_by = uuid.UUID(user_id) if user_id != "system" else None
            updated += 1
        except Exception as e:
            failures.append({"id": str(did), "reason": str(e)})

    await db.flush()
    return {
        "updated_count": updated,
        "failed_count": len(failures),
        "failures": failures,
    }


async def get_department_confirmations(
    db: AsyncSession,
    week_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List department weekly confirmations."""
    query = select(DepartmentWeeklyConfirmation).where(
        DepartmentWeeklyConfirmation.is_deleted.is_(False)
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
        "items": [
            DepartmentWeeklyConfirmationOut.model_validate(item).model_dump()
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def confirm_production_status(
    db: AsyncSession,
    data: Any,
    user_id: str,
) -> dict[str, bool]:
    """Create or update a department weekly confirmation."""
    query = select(DepartmentWeeklyConfirmation).where(
        DepartmentWeeklyConfirmation.department == data.department,
        DepartmentWeeklyConfirmation.week_key == data.week_key,
        DepartmentWeeklyConfirmation.is_deleted.is_(False),
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    now = datetime.now(UTC)
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
        DepartmentWeeklyConfirmation.is_deleted.is_(False),
    )
    result = await db.execute(query)
    return [row[0] for row in result.all()]
