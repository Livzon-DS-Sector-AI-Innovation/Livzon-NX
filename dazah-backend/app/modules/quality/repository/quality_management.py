"""Quality management database queries."""

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import (
    CAPA,
    AttachmentReview,
    CapaPlanTrack,
    ChangeActionPlan,
    ChangeControl,
    DepartmentContact,
    DepartmentWeeklyConfirmation,
    Deviation,
    DeviationInvestigationPushRecord,
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Deviation repository
async def exists_by_deviation_code(
    db: AsyncSession, deviation_code: str, exclude_id: uuid.UUID | None = None
) -> bool:
    query = select(Deviation.id).where(
        Deviation.deviation_code == deviation_code,
        Deviation.is_deleted == False,
    )
    if exclude_id:
        query = query.where(Deviation.id != exclude_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def create_deviation(db: AsyncSession, data: dict[str, Any]) -> Deviation:
    deviation = Deviation(**data)
    db.add(deviation)
    await db.flush()
    return deviation


async def get_deviation_by_id(db: AsyncSession, deviation_id: uuid.UUID) -> Deviation | None:
    result = await db.execute(
        select(Deviation).where(
            Deviation.id == deviation_id,
            Deviation.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_deviation_by_code(db: AsyncSession, deviation_code: str) -> Deviation | None:
    result = await db.execute(
        select(Deviation).where(
            Deviation.deviation_code == deviation_code,
            Deviation.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_deviations_by_codes(
    db: AsyncSession, deviation_codes: list[str]
) -> list[Deviation]:
    normalized_codes = [code for code in deviation_codes if code]
    if not normalized_codes:
        return []
    result = await db.execute(
        select(Deviation).where(
            Deviation.deviation_code.in_(normalized_codes),
            Deviation.is_deleted == False,
        )
    )
    return result.scalars().all()


async def get_deviations(
    db: AsyncSession,
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
    reporter_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    deviation_code: str | None = None,
    product_keyword: str | None = None,
    has_occurred_before: bool | None = None,
    is_closed: bool | None = None,
    investigation_completed_from: datetime | None = None,
    investigation_completed_to: datetime | None = None,
    root_cause_keyword: str | None = None,
    corrective_actions_keyword: str | None = None,
) -> tuple[list[Deviation], int]:
    query = select(Deviation).where(Deviation.is_deleted == False)
    count_query = select(func.count()).select_from(Deviation).where(
        Deviation.is_deleted == False
    )

    filters = []
    if status:
        filters.append(Deviation.status == status)
    if level:
        filters.append(Deviation.level == level)
    if department:
        filters.append(Deviation.department == department)
    if reporter_id:
        filters.append(Deviation.reporter_id == reporter_id)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters.append(
            or_(
                Deviation.deviation_code.ilike(pattern),
                Deviation.title.ilike(pattern),
                Deviation.description.ilike(pattern),
            )
        )
    if deviation_code:
        filters.append(
            Deviation.deviation_code.ilike(f"%{_escape_like(deviation_code)}%")
        )
    if product_keyword:
        pattern = f"%{_escape_like(product_keyword)}%"
        filters.append(
            or_(
                Deviation.affected_items.ilike(pattern),
                Deviation.batch_number.ilike(pattern),
            )
        )
    if has_occurred_before is not None:
        filters.append(Deviation.has_occurred_before == has_occurred_before)
    if is_closed is not None:
        filters.append(
            Deviation.status == "closed"
            if is_closed
            else Deviation.status != "closed"
        )
    if investigation_completed_from:
        filters.append(
            Deviation.investigation_completed_at >= investigation_completed_from
        )
    if investigation_completed_to:
        filters.append(
            Deviation.investigation_completed_at < investigation_completed_to
        )
    if root_cause_keyword:
        filters.append(
            Deviation.root_cause_analysis.ilike(
                f"%{_escape_like(root_cause_keyword)}%"
            )
        )
    if corrective_actions_keyword:
        filters.append(
            Deviation.corrective_actions.ilike(
                f"%{_escape_like(corrective_actions_keyword)}%"
            )
        )

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Deviation.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def update_deviation(
    db: AsyncSession, deviation: Deviation, data: dict[str, Any]
) -> Deviation:
    for key, value in data.items():
        setattr(deviation, key, value)
    await db.flush()
    return deviation


async def delete_deviation(db: AsyncSession, deviation: Deviation) -> None:
    deviation.is_deleted = True
    await db.flush()


# CAPA repository
async def exists_by_capa_code(
    db: AsyncSession, capa_code: str, exclude_id: uuid.UUID | None = None
) -> bool:
    query = select(CAPA.id).where(
        CAPA.capa_code == capa_code,
        CAPA.is_deleted == False,
    )
    if exclude_id:
        query = query.where(CAPA.id != exclude_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def create_capa(db: AsyncSession, data: dict[str, Any]) -> CAPA:
    capa = CAPA(**data)
    db.add(capa)
    await db.flush()
    return capa


async def get_capa_by_id(db: AsyncSession, capa_id: uuid.UUID) -> CAPA | None:
    result = await db.execute(
        select(CAPA).where(CAPA.id == capa_id, CAPA.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_capa_by_code(db: AsyncSession, capa_code: str) -> CAPA | None:
    result = await db.execute(
        select(CAPA).where(CAPA.capa_code == capa_code, CAPA.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_capas(
    db: AsyncSession,
    status: str | None = None,
    source: str | None = None,
    category: str | None = None,
    deviation_id: uuid.UUID | None = None,
    keyword: str | None = None,
    capa_code: str | None = None,
    affected_product: str | None = None,
    source_code: str | None = None,
    evaluation_result: str | None = None,
    closure_date_from: datetime | None = None,
    closure_date_to: datetime | None = None,
    department: str | None = None,
    qa_confirmer: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CAPA], int]:
    query = select(CAPA).where(CAPA.is_deleted == False)
    count_query = select(func.count()).select_from(CAPA).where(CAPA.is_deleted == False)

    filters = []
    if status:
        filters.append(CAPA.status == status)
    if source:
        filters.append(CAPA.source == source)
    if category:
        filters.append(CAPA.category == category)
    if deviation_id:
        filters.append(CAPA.deviation_id == deviation_id)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters.append(
            or_(CAPA.capa_code.ilike(pattern), CAPA.title.ilike(pattern))
        )
    if capa_code:
        filters.append(CAPA.capa_code.ilike(f"%{_escape_like(capa_code)}%"))
    if affected_product:
        filters.append(CAPA.affected_product.ilike(f"%{_escape_like(affected_product)}%"))
    if source_code:
        filters.append(CAPA.source_code.ilike(f"%{_escape_like(source_code)}%"))
    if evaluation_result:
        filters.append(CAPA.evaluation_result.ilike(f"%{_escape_like(evaluation_result)}%"))
    if closure_date_from:
        filters.append(CAPA.closure_date >= closure_date_from)
    if closure_date_to:
        filters.append(CAPA.closure_date < closure_date_to)
    if department:
        filters.append(CAPA.department.ilike(f"%{_escape_like(department)}%"))
    if qa_confirmer:
        filters.append(CAPA.qa_confirmer.ilike(f"%{_escape_like(qa_confirmer)}%"))

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(CAPA.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def update_capa(db: AsyncSession, capa: CAPA, data: dict[str, Any]) -> CAPA:
    for key, value in data.items():
        setattr(capa, key, value)
    await db.flush()
    return capa


async def delete_capa(db: AsyncSession, capa: CAPA) -> None:
    capa.is_deleted = True
    await db.flush()


# Change Control repository
async def exists_by_change_code(
    db: AsyncSession, change_code: str, exclude_id: uuid.UUID | None = None
) -> bool:
    query = select(ChangeControl.id).where(
        ChangeControl.change_code == change_code,
        ChangeControl.is_deleted == False,
    )
    if exclude_id:
        query = query.where(ChangeControl.id != exclude_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def create_change(db: AsyncSession, data: dict[str, Any]) -> ChangeControl:
    change = ChangeControl(**data)
    db.add(change)
    await db.flush()
    return change


async def get_change_by_id(
    db: AsyncSession, change_id: uuid.UUID
) -> ChangeControl | None:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id,
            ChangeControl.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_change_by_code(
    db: AsyncSession, change_code: str
) -> ChangeControl | None:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.change_code == change_code,
            ChangeControl.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def list_change_codes_by_prefix(
    db: AsyncSession, change_code_prefix: str
) -> list[str]:
    result = await db.execute(
        select(ChangeControl.change_code).where(
            ChangeControl.change_code.like(f"{change_code_prefix}%")
        )
    )
    return [row[0] for row in result.all() if row[0]]


async def get_changes(
    db: AsyncSession,
    change_code: str | None = None,
    applicant_department: str | None = None,
    change_object: str | None = None,
    change_level: str | None = None,
    application_date_from: date | None = None,
    application_date_to: date | None = None,
    planned_approval_date_from: date | None = None,
    planned_approval_date_to: date | None = None,
    execution_date_from: date | None = None,
    execution_date_to: date | None = None,
    closure_date_from: date | None = None,
    closure_date_to: date | None = None,
    content_keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ChangeControl], int]:
    query = select(ChangeControl).where(ChangeControl.is_deleted == False)
    count_query = select(func.count()).select_from(ChangeControl).where(
        ChangeControl.is_deleted == False
    )

    filters = []
    if change_code:
        filters.append(
            ChangeControl.change_code.ilike(f"%{_escape_like(change_code)}%")
        )
    if applicant_department:
        filters.append(
            ChangeControl.applicant_department.ilike(
                f"%{_escape_like(applicant_department)}%"
            )
        )
    if change_object:
        filters.append(
            ChangeControl.change_object.ilike(f"%{_escape_like(change_object)}%")
        )
    if change_level:
        filters.append(ChangeControl.change_level == change_level)
    if application_date_from:
        filters.append(ChangeControl.application_date >= application_date_from)
    if application_date_to:
        filters.append(ChangeControl.application_date <= application_date_to)
    if planned_approval_date_from:
        filters.append(
            ChangeControl.planned_approval_date >= planned_approval_date_from
        )
    if planned_approval_date_to:
        filters.append(
            ChangeControl.planned_approval_date <= planned_approval_date_to
        )
    if execution_date_from:
        filters.append(ChangeControl.execution_date >= execution_date_from)
    if execution_date_to:
        filters.append(ChangeControl.execution_date <= execution_date_to)
    if closure_date_from:
        filters.append(ChangeControl.closure_date >= closure_date_from)
    if closure_date_to:
        filters.append(ChangeControl.closure_date <= closure_date_to)
    if content_keyword:
        filters.append(
            ChangeControl.change_content.ilike(f"%{_escape_like(content_keyword)}%")
        )

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(ChangeControl.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def update_change(
    db: AsyncSession, change: ChangeControl, data: dict[str, Any]
) -> ChangeControl:
    for key, value in data.items():
        setattr(change, key, value)
    await db.flush()
    return change


async def delete_change(db: AsyncSession, change: ChangeControl) -> None:
    change.is_deleted = True
    await db.flush()


# Change Action Plan repository
async def get_change_action_plan_counts_by_change_ids(
    db: AsyncSession, change_ids: list[uuid.UUID]
) -> dict[str, int]:
    if not change_ids:
        return {}
    q = (
        select(
            ChangeActionPlan.change_id,
            func.count(ChangeActionPlan.id),
        )
        .where(
            ChangeActionPlan.change_id.in_(change_ids),
            ChangeActionPlan.is_deleted == False,
        )
        .group_by(ChangeActionPlan.change_id)
    )
    rows = (await db.execute(q)).all()
    return {str(row[0]): row[1] for row in rows}


async def create_change_action_plan(
    db: AsyncSession, data: dict[str, Any]
) -> ChangeActionPlan:
    plan = ChangeActionPlan(**data)
    db.add(plan)
    await db.flush()
    return plan


async def get_change_action_plan_by_id(
    db: AsyncSession, plan_id: uuid.UUID
) -> ChangeActionPlan | None:
    result = await db.execute(
        select(ChangeActionPlan).where(
            ChangeActionPlan.id == plan_id,
            ChangeActionPlan.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_change_action_plan_by_feishu_record_id(
    db: AsyncSession, feishu_record_id: str
) -> ChangeActionPlan | None:
    result = await db.execute(
        select(ChangeActionPlan).where(
            ChangeActionPlan.feishu_record_id == feishu_record_id,
            ChangeActionPlan.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_change_action_plan_by_match_fields(
    db: AsyncSession,
    *,
    change_code: str,
    project_name: str,
    related_work: str | None,
) -> ChangeActionPlan | None:
    result = await db.execute(
        select(ChangeActionPlan).where(
            ChangeActionPlan.change_code == change_code,
            ChangeActionPlan.project_name == project_name,
            ChangeActionPlan.related_work == related_work,
            ChangeActionPlan.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_change_action_plans(
    db: AsyncSession,
    *,
    change_id: uuid.UUID | None = None,
    change_code: str | None = None,
    project_name: str | None = None,
    related_work: str | None = None,
    owner_name: str | None = None,
    director_name: str | None = None,
    status: str | None = None,
    delay_flag: str | None = None,
    sync_status: str | None = None,
    deadline_date_from: date | None = None,
    deadline_date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ChangeActionPlan], int]:
    query = select(ChangeActionPlan).where(ChangeActionPlan.is_deleted == False)
    count_query = select(func.count()).select_from(ChangeActionPlan).where(
        ChangeActionPlan.is_deleted == False
    )

    filters = []
    if change_id:
        filters.append(ChangeActionPlan.change_id == change_id)
    if change_code:
        filters.append(
            ChangeActionPlan.change_code.ilike(f"%{_escape_like(change_code)}%")
        )
    if project_name:
        filters.append(
            ChangeActionPlan.project_name.ilike(f"%{_escape_like(project_name)}%")
        )
    if related_work:
        filters.append(
            ChangeActionPlan.related_work.ilike(f"%{_escape_like(related_work)}%")
        )
    if owner_name:
        filters.append(
            ChangeActionPlan.owner_name.ilike(f"%{_escape_like(owner_name)}%")
        )
    if director_name:
        filters.append(
            ChangeActionPlan.director_name.ilike(f"%{_escape_like(director_name)}%")
        )
    if status:
        filters.append(ChangeActionPlan.status == status)
    if delay_flag:
        filters.append(ChangeActionPlan.delay_flag == delay_flag)
    if sync_status:
        filters.append(ChangeActionPlan.sync_status == sync_status)
    if deadline_date_from:
        filters.append(ChangeActionPlan.deadline_date >= deadline_date_from)
    if deadline_date_to:
        filters.append(ChangeActionPlan.deadline_date <= deadline_date_to)

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(ChangeActionPlan.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def update_change_action_plan(
    db: AsyncSession, plan: ChangeActionPlan, data: dict[str, Any]
) -> ChangeActionPlan:
    for key, value in data.items():
        setattr(plan, key, value)
    await db.flush()
    return plan


async def delete_change_action_plan(
    db: AsyncSession, plan: ChangeActionPlan
) -> None:
    plan.is_deleted = True
    await db.flush()


async def create_deviation_investigation_push_record(
    db: AsyncSession, data: dict[str, Any]
) -> DeviationInvestigationPushRecord:
    record = DeviationInvestigationPushRecord(**data)
    db.add(record)
    await db.flush()
    return record


async def get_deviation_investigation_push_record_by_id(
    db: AsyncSession, record_id: uuid.UUID
) -> DeviationInvestigationPushRecord | None:
    result = await db.execute(
        select(DeviationInvestigationPushRecord).where(
            DeviationInvestigationPushRecord.id == record_id,
            DeviationInvestigationPushRecord.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_deviation_investigation_push_records(
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
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DeviationInvestigationPushRecord], int]:
    query = select(DeviationInvestigationPushRecord).where(
        DeviationInvestigationPushRecord.is_deleted == False
    )
    count_query = select(func.count()).select_from(
        DeviationInvestigationPushRecord
    ).where(DeviationInvestigationPushRecord.is_deleted == False)

    filters = []
    if deviation_id:
        filters.append(DeviationInvestigationPushRecord.deviation_id == deviation_id)
    if deviation_code:
        filters.append(
            DeviationInvestigationPushRecord.deviation_code.ilike(
                f"%{_escape_like(deviation_code)}%"
            )
        )
    if push_round:
        filters.append(DeviationInvestigationPushRecord.push_round == push_round)
    if submitter:
        filters.append(
            DeviationInvestigationPushRecord.submitter.ilike(
                f"%{_escape_like(submitter)}%"
            )
        )
    if department_head_result:
        filters.append(
            DeviationInvestigationPushRecord.department_head_result
            == department_head_result
        )
    if qa_result:
        filters.append(DeviationInvestigationPushRecord.qa_result == qa_result)
    if qa_head_result:
        filters.append(
            DeviationInvestigationPushRecord.qa_head_result == qa_head_result
        )
    if submitted_at_from:
        filters.append(DeviationInvestigationPushRecord.submitted_at >= submitted_at_from)
    if submitted_at_to:
        filters.append(DeviationInvestigationPushRecord.submitted_at < submitted_at_to)

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(DeviationInvestigationPushRecord.submitted_at.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all(), total


async def get_latest_deviation_investigation_push_records_by_deviation_ids(
    db: AsyncSession,
    deviation_ids: list[uuid.UUID],
) -> list[DeviationInvestigationPushRecord]:
    if not deviation_ids:
        return []

    result = await db.execute(
        select(DeviationInvestigationPushRecord)
        .where(
            DeviationInvestigationPushRecord.is_deleted == False,
            DeviationInvestigationPushRecord.deviation_id.in_(deviation_ids),
        )
        .order_by(
            DeviationInvestigationPushRecord.deviation_id.asc(),
            DeviationInvestigationPushRecord.submitted_at.desc().nullslast(),
            DeviationInvestigationPushRecord.updated_at.desc(),
            DeviationInvestigationPushRecord.created_at.desc(),
        )
    )
    records = result.scalars().all()

    latest_records: list[DeviationInvestigationPushRecord] = []
    seen: set[uuid.UUID] = set()
    for record in records:
        if record.deviation_id in seen:
            continue
        seen.add(record.deviation_id)
        latest_records.append(record)
    return latest_records


async def get_deviation_investigation_push_record_by_deviation_and_round(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    push_round: str,
) -> DeviationInvestigationPushRecord | None:
    result = await db.execute(
        select(DeviationInvestigationPushRecord).where(
            DeviationInvestigationPushRecord.is_deleted == False,
            DeviationInvestigationPushRecord.deviation_id == deviation_id,
            DeviationInvestigationPushRecord.push_round == push_round,
        )
    )
    return result.scalar_one_or_none()


async def get_deviation_investigation_push_records_by_codes(
    db: AsyncSession,
    deviation_codes: list[str],
) -> list[DeviationInvestigationPushRecord]:
    if not deviation_codes:
        return []
    result = await db.execute(
        select(DeviationInvestigationPushRecord).where(
            DeviationInvestigationPushRecord.is_deleted == False,
            DeviationInvestigationPushRecord.deviation_code.in_(deviation_codes),
        )
    )
    return result.scalars().all()


async def update_deviation_investigation_push_record(
    db: AsyncSession,
    record: DeviationInvestigationPushRecord,
    data: dict[str, Any],
) -> DeviationInvestigationPushRecord:
    for key, value in data.items():
        setattr(record, key, value)
    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return record


async def create_capa_plan_track(
    db: AsyncSession, data: dict[str, Any]
) -> CapaPlanTrack:
    record = CapaPlanTrack(**data)
    db.add(record)
    await db.flush()
    return record


async def get_capa_plan_track_by_id(
    db: AsyncSession, track_id: uuid.UUID
) -> CapaPlanTrack | None:
    result = await db.execute(
        select(CapaPlanTrack).where(
            CapaPlanTrack.id == track_id,
            CapaPlanTrack.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_capa_plan_tracks(
    db: AsyncSession,
    *,
    capa_id: uuid.UUID | None = None,
    capa_code: str | None = None,
    progress: str | None = None,
    owner_name: str | None = None,
    reminder_status: str | None = None,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CapaPlanTrack], int]:
    query = select(CapaPlanTrack).where(CapaPlanTrack.is_deleted == False)
    count_query = select(func.count()).select_from(CapaPlanTrack).where(
        CapaPlanTrack.is_deleted == False
    )

    filters = []
    if capa_id:
        filters.append(CapaPlanTrack.capa_id == capa_id)
    if capa_code:
        filters.append(CapaPlanTrack.capa_code.ilike(f"%{_escape_like(capa_code)}%"))
    if progress:
        filters.append(CapaPlanTrack.progress == progress)
    if owner_name:
        filters.append(CapaPlanTrack.owner_name.ilike(f"%{_escape_like(owner_name)}%"))
    if reminder_status:
        filters.append(CapaPlanTrack.reminder_status == reminder_status)
    if due_date_from:
        filters.append(CapaPlanTrack.due_date >= due_date_from)
    if due_date_to:
        filters.append(CapaPlanTrack.due_date <= due_date_to)

    for filter_condition in filters:
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(CapaPlanTrack.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all(), total


async def get_capa_plan_tracks_by_capa_ids(
    db: AsyncSession,
    capa_ids: list[uuid.UUID],
) -> list[CapaPlanTrack]:
    if not capa_ids:
        return []
    result = await db.execute(
        select(CapaPlanTrack)
        .where(
            CapaPlanTrack.is_deleted == False,
            CapaPlanTrack.capa_id.in_(capa_ids),
        )
        .order_by(CapaPlanTrack.updated_at.desc())
    )
    return result.scalars().all()


async def update_capa_plan_track(
    db: AsyncSession,
    track: CapaPlanTrack,
    data: dict[str, Any],
) -> CapaPlanTrack:
    for key, value in data.items():
        setattr(track, key, value)
    track.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return track


# Department Contact repository
async def get_department_contact_by_id(
    db: AsyncSession, contact_id: uuid.UUID
) -> DepartmentContact | None:
    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.id == contact_id,
            DepartmentContact.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_department_contact_by_department(
    db: AsyncSession, department: str
) -> DepartmentContact | None:
    result = await db.execute(
        select(DepartmentContact).where(
            DepartmentContact.department == department,
            DepartmentContact.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_department_contacts(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> tuple[list[DepartmentContact], int]:
    query = select(DepartmentContact).where(DepartmentContact.is_deleted == False)
    count_query = (
        select(func.count())
        .select_from(DepartmentContact)
        .where(DepartmentContact.is_deleted == False)
    )

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(DepartmentContact.department).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def create_department_contact(
    db: AsyncSession, data: dict[str, Any]
) -> DepartmentContact:
    contact = DepartmentContact(**data)
    db.add(contact)
    await db.flush()
    return contact


async def update_department_contact(
    db: AsyncSession, contact: DepartmentContact, data: dict[str, Any]
) -> DepartmentContact:
    for key, value in data.items():
        setattr(contact, key, value)
    await db.flush()
    return contact


async def delete_department_contact(
    db: AsyncSession, contact: DepartmentContact
) -> None:
    contact.is_deleted = True
    await db.flush()


# Department Weekly Confirmation repository
async def get_weekly_confirmation_by_id(
    db: AsyncSession, confirmation_id: uuid.UUID
) -> DepartmentWeeklyConfirmation | None:
    result = await db.execute(
        select(DepartmentWeeklyConfirmation).where(
            DepartmentWeeklyConfirmation.id == confirmation_id,
            DepartmentWeeklyConfirmation.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_weekly_confirmation_by_department_week(
    db: AsyncSession, department: str, week_key: str
) -> DepartmentWeeklyConfirmation | None:
    result = await db.execute(
        select(DepartmentWeeklyConfirmation).where(
            DepartmentWeeklyConfirmation.department == department,
            DepartmentWeeklyConfirmation.week_key == week_key,
            DepartmentWeeklyConfirmation.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_weekly_confirmations(
    db: AsyncSession,
    department: str | None = None,
    week_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DepartmentWeeklyConfirmation], int]:
    query = select(DepartmentWeeklyConfirmation).where(
        DepartmentWeeklyConfirmation.is_deleted == False
    )
    count_query = (
        select(func.count())
        .select_from(DepartmentWeeklyConfirmation)
        .where(DepartmentWeeklyConfirmation.is_deleted == False)
    )

    if department:
        query = query.where(DepartmentWeeklyConfirmation.department == department)
        count_query = count_query.where(
            DepartmentWeeklyConfirmation.department == department
        )
    if week_key:
        query = query.where(DepartmentWeeklyConfirmation.week_key == week_key)
        count_query = count_query.where(
            DepartmentWeeklyConfirmation.week_key == week_key
        )

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(DepartmentWeeklyConfirmation.confirmed_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def create_weekly_confirmation(
    db: AsyncSession, data: dict[str, Any]
) -> DepartmentWeeklyConfirmation:
    confirmation = DepartmentWeeklyConfirmation(**data)
    db.add(confirmation)
    await db.flush()
    return confirmation


async def update_weekly_confirmation(
    db: AsyncSession,
    confirmation: DepartmentWeeklyConfirmation,
    data: dict[str, Any],
) -> DepartmentWeeklyConfirmation:
    for key, value in data.items():
        setattr(confirmation, key, value)
    await db.flush()
    return confirmation


async def delete_weekly_confirmation(
    db: AsyncSession, confirmation: DepartmentWeeklyConfirmation
) -> None:
    confirmation.is_deleted = True
    await db.flush()


# Attachment Review repository
async def get_attachment_review_by_id(
    db: AsyncSession, review_id: uuid.UUID
) -> AttachmentReview | None:
    result = await db.execute(
        select(AttachmentReview).where(
            AttachmentReview.id == review_id,
            AttachmentReview.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def get_attachment_reviews(
    db: AsyncSession,
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AttachmentReview], int]:
    query = select(AttachmentReview).where(AttachmentReview.is_deleted == False)
    count_query = (
        select(func.count())
        .select_from(AttachmentReview)
        .where(AttachmentReview.is_deleted == False)
    )

    if deviation_id:
        query = query.where(AttachmentReview.deviation_id == deviation_id)
        count_query = count_query.where(AttachmentReview.deviation_id == deviation_id)
    if capa_id:
        query = query.where(AttachmentReview.capa_id == capa_id)
        count_query = count_query.where(AttachmentReview.capa_id == capa_id)
    if attachment_url:
        query = query.where(AttachmentReview.attachment_url == attachment_url)
        count_query = count_query.where(
            AttachmentReview.attachment_url == attachment_url
        )

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(AttachmentReview.review_time.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def create_attachment_review(
    db: AsyncSession, data: dict[str, Any]
) -> AttachmentReview:
    review = AttachmentReview(**data)
    db.add(review)
    await db.flush()
    return review


async def update_attachment_review(
    db: AsyncSession, review: AttachmentReview, data: dict[str, Any]
) -> AttachmentReview:
    for key, value in data.items():
        setattr(review, key, value)
    await db.flush()
    return review


async def delete_attachment_review(
    db: AsyncSession, review: AttachmentReview
) -> None:
    review.is_deleted = True
    await db.flush()


# Deviation <-> CAPA link repository
async def get_related_capas_for_deviation(
    db: AsyncSession,
    deviation_id: uuid.UUID,
    deviation_code: str,
) -> list[CAPA]:
    """Return CAPAs linked to a deviation by three precise matching rules.

    Priority:
    1. CAPA.deviation_id == deviation_id
    2. CAPA.source == 'deviation' and CAPA.source_code == deviation_code
    3. CAPA.capa_code == 'CAPA-{deviation_code}'
    """
    from sqlalchemy import case

    expected_capa_code = f"CAPA-{deviation_code}"
    priority = case(
        (CAPA.deviation_id == deviation_id, 1),
        (
            (CAPA.source == "deviation") & (CAPA.source_code == deviation_code),
            2,
        ),
        (CAPA.capa_code == expected_capa_code, 3),
        else_=99,
    )
    query = (
        select(CAPA)
        .where(CAPA.is_deleted == False)
        .where(
            or_(
                CAPA.deviation_id == deviation_id,
                ((CAPA.source == "deviation") & (CAPA.source_code == deviation_code)),
                CAPA.capa_code == expected_capa_code,
            )
        )
        .order_by(priority.asc(), CAPA.updated_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()
