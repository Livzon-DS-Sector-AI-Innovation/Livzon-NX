"""变更（Change）业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality import repository
from app.modules.quality.models import (
    ChangeControl,
)
from app.modules.quality.schemas import (
    ChangeDetail,
    ChangeListItem,
    CreateChangeRequest,
    UpdateChangeRequest,
)
from app.modules.quality.service.quality_common import (
    _build_page_result,
    _parse_date_filter,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.models import User

logger = logging.getLogger(__name__)


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


async def get_change_list(
    db: AsyncSession,
    change_code: str | None = None,
    change_type: str | None = None,
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
    scope: DepartmentScope | None = None,
) -> dict[str, Any]:
    items, total = await repository.get_changes(
        db,
        change_code=change_code,
        change_type=change_type,
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
        scope=scope,
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
            ChangeControl.id == change_id, ChangeControl.is_deleted.is_(False)
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise NotFoundException(resource="变更", resource_id=str(change_id))
    return ChangeDetail.model_validate(change)


async def create_change(
    db: AsyncSession, data: CreateChangeRequest, user_id: str
) -> dict[str, str]:
    change = ChangeControl(
        change_type=data.change_type,
        serial_number=data.serial_number,
        change_code=data.change_code,
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
    result = await db.execute(
        select(ChangeControl).where(ChangeControl.id == change.id)
    )
    change = result.scalar_one()
    return {"id": str(change.id), "code": change.change_code}


async def update_change(
    db: AsyncSession, change_id: uuid.UUID, data: UpdateChangeRequest, user_id: str
) -> dict[str, bool]:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id, ChangeControl.is_deleted.is_(False)
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise NotFoundException(resource="变更", resource_id=str(change_id))

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(change, field, value)

    change.updated_at = datetime.now(UTC)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}


async def delete_change(
    db: AsyncSession, change_id: uuid.UUID, deleted_by: uuid.UUID | None = None
) -> dict[str, bool]:
    result = await db.execute(
        select(ChangeControl).where(
            ChangeControl.id == change_id, ChangeControl.is_deleted.is_(False)
        )
    )
    change = result.scalar_one_or_none()
    if not change:
        raise NotFoundException(resource="变更", resource_id=str(change_id))

    change.is_deleted = True
    change.deleted_by = deleted_by
    change.deleted_at = datetime.now(UTC)
    change.updated_at = datetime.now(UTC)
    audit_user_id = deleted_by
    if deleted_by is not None:
        user_result = await db.execute(select(User.id).where(User.id == deleted_by))
        audit_user_id = user_result.scalar_one_or_none()
    await record_audit_log(
        db,
        action="delete",
        user_id=audit_user_id,
        resource_type="quality.change_control",
        resource_id=change.id,
        old_value={
            "change_code": change.change_code,
            "change_level": change.change_level,
            "change_object": change.change_object,
        },
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"success": True}


async def generate_next_change_code(
    db: AsyncSession, change_type: str = "technical"
) -> str:
    """生成下一个变更控制号。

    technical: BG-{YY}{MM}{NNN}（如 BG-2603024），按月独立流水
    file:      BG-{YY}{MM}{NNN}-F（如 BG-2603001-F），独立流水，不与技术变更共用
    """
    now = datetime.now(UTC)
    yymm = now.strftime("%y%m")
    suffix = "-F" if change_type == "file" else ""
    if change_type == "file":
        pattern = re.compile(rf"^BG-{yymm}(\d{{3}})-F$")
    else:
        pattern = re.compile(rf"^BG-{yymm}(\d{{3}})$")

    result = await db.execute(
        select(ChangeControl.change_code).where(
            ChangeControl.change_code.like(f"BG-{yymm}%"),
            ChangeControl.is_deleted.is_(False),
        )
    )
    max_seq = 0
    for code in result.scalars().all():
        match = pattern.match(code or "")
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    seq = max_seq + 1
    return f"BG-{yymm}{seq:03d}{suffix}"
