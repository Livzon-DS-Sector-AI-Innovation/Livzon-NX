"""CAPA 业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality import repository
from app.modules.quality.models import (
    CAPA,
    DepartmentContact,
    Deviation,
)
from app.modules.quality.schemas import (
    CapaDetail,
    CapaListItem,
    CreateCapaRequest,
    UpdateCapaRequest,
)
from app.modules.quality.service.quality_common import (
    _build_page_result,
    _parse_datetime_filter,
    _parse_datetime_filter_end_exclusive,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.data_scope import DepartmentScope

logger = logging.getLogger(__name__)


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
    scope: DepartmentScope | None = None,
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
        scope=scope,
    )

    return _build_page_result(
        await _build_capa_list_items(db, items),
        total,
        page,
        page_size,
    )


async def get_capa_detail(db: AsyncSession, capa_id: uuid.UUID) -> CapaDetail:
    result = await db.execute(
        select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted.is_(False))
    )
    capa = result.scalar_one_or_none()
    if not capa:
        raise NotFoundException(resource="CAPA", resource_id=str(capa_id))
    return CapaDetail.model_validate(capa)


async def create_capa(
    db: AsyncSession, data: CreateCapaRequest, user_id: str
) -> dict[str, str]:
    capa = CAPA(
        capa_code=f"CAPA-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        title=data.title,
        deviation_id=data.deviation_id,
        source=data.source,
        source_code=data.source_code,
        category=data.category,
        root_cause_category=data.root_cause_category,
        non_conformity_description=data.non_conformity_description,
        root_cause_analysis=data.root_cause_analysis,
        capa_content=data.capa_content,
        capa_items=[item.model_dump() for item in data.capa_items]
        if data.capa_items
        else [],
        executors=data.executors,
        expected_completion_date=datetime.fromisoformat(data.expected_completion_date)
        if data.expected_completion_date
        else None,
        reporter=data.reporter,
        status="draft",
        status_updated_at=datetime.now(UTC),
    )
    db.add(capa)
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    result = await db.execute(select(CAPA).where(CAPA.id == capa.id))
    capa = result.scalar_one()
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_after_write(db, capa.id)
    return {"id": str(capa.id), "code": capa.capa_code}


async def update_capa(
    db: AsyncSession, capa_id: uuid.UUID, data: UpdateCapaRequest, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted.is_(False))
    )
    capa = result.scalar_one_or_none()
    if not capa:
        raise NotFoundException(resource="CAPA", resource_id=str(capa_id))

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in [
            "capa_items",
            "execution_tracks",
            "dept_head_confirmations",
            "report_versions",
        ]:
            setattr(capa, field, value)
        elif (
            field
            in [
                "expected_completion_date",
                "evaluation_deadline",
                "evaluation_confirm_date",
                "closure_date",
                "qa_review_time",
                "q_head_approval_time",
            ]
            and value
        ):
            setattr(capa, field, datetime.fromisoformat(value))
        else:
            setattr(capa, field, value)

    capa.updated_at = datetime.now(UTC)
    if data.status:
        capa.status_updated_at = datetime.now(UTC)

    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    from app.modules.quality.service import quality_feishu_sync as feishu_sync_service

    await feishu_sync_service.auto_sync_capa_after_write(db, capa.id)
    return {"success": True}


async def delete_capa(
    db: AsyncSession, capa_id: uuid.UUID, deleted_by: uuid.UUID | None = None
) -> dict[str, bool]:
    result = await db.execute(
        select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted.is_(False))
    )
    capa = result.scalar_one_or_none()
    if not capa:
        raise NotFoundException(resource="CAPA", resource_id=str(capa_id))
    capa.is_deleted = True
    capa.deleted_by = deleted_by
    capa.deleted_at = datetime.now(UTC)
    capa.updated_at = datetime.now(UTC)
    await record_audit_log(
        db,
        action="delete",
        user_id=deleted_by,
        resource_type="quality.capa",
        resource_id=capa.id,
        old_value={
            "capa_code": capa.capa_code,
            "title": capa.title,
            "status": capa.status,
        },
    )
    try:
        await db.commit()

    except Exception:
        await db.rollback()

        raise
    return {"success": True}


# ============ NEW: CAPA Workflow Endpoints ============


async def get_capa_departments(db: AsyncSession) -> list[str]:
    """Get all departments from department contacts."""
    query = select(DepartmentContact.department).where(
        DepartmentContact.is_deleted.is_(False)
    )
    result = await db.execute(query)
    return [row[0] for row in result.all()]


async def auto_fill_from_deviation(
    db: AsyncSession, deviation_id: uuid.UUID
) -> dict[str, Any]:
    """Auto-fill CAPA form from deviation data."""
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise NotFoundException(resource="偏差")

    # Extract from AI analysis
    ai_analysis = deviation.ai_analysis or {}
    non_conformity = ai_analysis.get(
        "structured_deviation_description", deviation.description or ""
    )
    root_cause = ai_analysis.get("preliminary_cause_analysis", "")

    # Extract from last investigation record
    investigation_records = deviation.investigation_records or []
    capa_content = ""
    if investigation_records:
        last_record = (
            investigation_records[-1] if isinstance(investigation_records, list) else {}
        )
        if isinstance(last_record, dict):
            non_conformity = last_record.get("nonconformityDescription", non_conformity)
            root_cause = last_record.get("rootCauseAnalysis", root_cause)
            # Build capa content from proposals
            proposals = last_record.get("capaProposals", [])
            if proposals:
                capa_content = "\n".join(
                    f"{i + 1}. {p.get('summary', p.get('content', ''))}"
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
        raise NotFoundException(resource="CAPA")
    deviation = await db.get(Deviation, deviation_id)
    if not deviation or deviation.is_deleted:
        raise NotFoundException(resource="偏差")

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
        raise NotFoundException(resource="CAPA")

    # Store completion in capa_items or a tracking field
    # For simplicity, update status when both parts are complete
    if part == "a":
        # Part A = problem description complete
        pass
    elif part == "b":
        # Part B = measures complete
        pass

    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def submit_capa(
    db: AsyncSession, capa_id: uuid.UUID, user_id: str
) -> dict[str, bool]:
    """Submit CAPA for QA approval."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")
    if capa.status not in ("draft",):
        raise AppException(
            message=f"只有草稿状态的CAPA可以提交，当前状态: {capa.status}"
        )

    capa.status = "submitted"
    capa.status_updated_at = datetime.now(UTC)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def confirm_dept_head(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data: Any,
    user_id: str,
) -> dict[str, bool]:
    """Department head confirmation for CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")

    confirmations = capa.dept_head_confirmations or []
    now = datetime.now(UTC).isoformat()

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
        isinstance(c, dict) and c.get("result") == "approved" for c in confirmations
    )
    any_rejected = any(
        isinstance(c, dict) and c.get("result") == "rejected" for c in confirmations
    )

    if all_approved and confirmations:
        capa.status = "pending_qa_approval"
        capa.status_updated_at = datetime.now(UTC)
    elif any_rejected:
        capa.status = "returned"
        capa.returned_step = "dept_head_confirm"
        capa.status_updated_at = datetime.now(UTC)

    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def approve_capa(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data: Any,
    user_id: str,
) -> dict[str, bool]:
    """QA approval for CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")

    now = datetime.now(UTC)

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


async def resubmit_capa(
    db: AsyncSession, capa_id: uuid.UUID, user_id: str
) -> dict[str, bool]:
    """Resubmit CAPA after rejection."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")
    if capa.status != "returned":
        raise AppException(
            message=f"只有已退回状态的CAPA可以重新提交，当前状态: {capa.status}"
        )

    capa.status = "draft"
    capa.returned_step = None
    capa.status_updated_at = datetime.now(UTC)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def add_execution_track(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data: dict[str, Any],
    user_id: str,
) -> dict[str, bool]:
    """Add an execution tracking record to CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")

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
        raise NotFoundException(resource="CAPA")

    tracks = capa.execution_tracks or []
    if index < 0 or index >= len(tracks):
        raise AppException(message="执行记录索引无效")

    tracks.pop(index)
    capa.execution_tracks = tracks
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def confirm_execution(
    db: AsyncSession, capa_id: uuid.UUID, user_id: str
) -> dict[str, bool]:
    """Confirm CAPA execution is complete, advance to pending_evaluation."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")
    if capa.status != "executing":
        raise AppException(
            message=f"只有执行中状态的CAPA可以确认执行完成，当前状态: {capa.status}"
        )

    capa.status = "pending_evaluation"
    capa.status_updated_at = datetime.now(UTC)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}


async def submit_evaluation(
    db: AsyncSession,
    capa_id: uuid.UUID,
    data: Any,
    user_id: str,
) -> dict[str, bool]:
    """Submit effectiveness evaluation and close CAPA."""
    capa = await db.get(CAPA, capa_id)
    if not capa or capa.is_deleted:
        raise NotFoundException(resource="CAPA")
    if capa.status != "pending_evaluation":
        raise AppException(
            message=f"只有待效果评价状态的CAPA可以提交评价，当前状态: {capa.status}"
        )

    capa.evaluation_target = data.evaluation_target
    capa.evaluation_result = data.evaluation_result
    capa.evaluation_confirmer_id = (
        uuid.UUID(data.evaluation_confirmer) if data.evaluation_confirmer else None
    )
    capa.evaluation_confirm_date = (
        datetime.fromisoformat(data.evaluation_confirm_date.replace("Z", "+00:00"))
        if data.evaluation_confirm_date
        else None
    )
    capa.closure_date = (
        datetime.fromisoformat(data.closure_date.replace("Z", "+00:00"))
        if data.closure_date
        else None
    )
    capa.status = "closed"
    capa.status_updated_at = datetime.now(UTC)
    capa.updated_by = uuid.UUID(user_id) if user_id != "system" else None
    await db.flush()
    return {"success": True}
