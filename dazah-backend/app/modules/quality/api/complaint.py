"""Complaint API endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import error_response, paginated_response, success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.complaint import ComplaintRecord
from app.modules.quality.schemas.complaint import (
    ComplaintOut,
    CreateComplaintRequest,
    UpdateComplaintRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/complaints",
    summary="获取投诉列表",
    response_model=ApiResponseEnvelope[list[ComplaintOut]],
)
async def list_complaints(
    status: str | None = Query(None, description="状态"),
    complaint_category: str | None = Query(None, description="投诉类别"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(ComplaintRecord).where(
            ComplaintRecord.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(ComplaintRecord)
            .where(ComplaintRecord.is_deleted.is_(False))
        )

        filters = []
        if status:
            filters.append(ComplaintRecord.status == status)
        if complaint_category:
            filters.append(ComplaintRecord.complaint_category == complaint_category)
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters.append(
                or_(
                    ComplaintRecord.complaint_code.ilike(pattern),
                    ComplaintRecord.title.ilike(pattern),
                    ComplaintRecord.description.ilike(pattern),
                )
            )

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        base_query = (
            base_query.order_by(ComplaintRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items_result = await db.execute(base_query)
        items = items_result.scalars().all()

        return paginated_response(
            data=[
                ComplaintOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list complaints")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.get(
    "/complaints/{complaint_id}",
    summary="获取投诉详情",
    response_model=ApiResponseEnvelope[ComplaintOut],
)
async def get_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.id == complaint_id,
                ComplaintRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)
        return success_response(
            data=ComplaintOut.model_validate(item).model_dump(mode="json")
        )
    except Exception:
        logger.exception("Failed to get complaint")
        return error_response(message="获取详情失败，请稍后重试", status_code=500)


@router.post(
    "/complaints",
    summary="创建投诉记录",
    response_model=ApiResponseEnvelope[ComplaintOut],
)
async def create_complaint(
    data: CreateComplaintRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = ComplaintRecord(**data.model_dump())
        db.add(record)
        await db.flush()
        result = await db.execute(
            select(ComplaintRecord).where(ComplaintRecord.id == record.id)
        )
        record = result.scalar_one()
        return success_response(
            data=ComplaintOut.model_validate(record).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create complaint")
        return error_response(message="创建失败，请稍后重试", status_code=400)


@router.put(
    "/complaints/{complaint_id}",
    summary="更新投诉记录",
    response_model=ApiResponseEnvelope[ComplaintOut],
)
async def update_complaint(
    complaint_id: uuid.UUID,
    data: UpdateComplaintRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.id == complaint_id,
                ComplaintRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        result = await db.execute(
            select(ComplaintRecord).where(ComplaintRecord.id == item.id)
        )
        item = result.scalar_one()
        return success_response(
            data=ComplaintOut.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update complaint")
        return error_response(message="更新失败，请稍后重试", status_code=400)


@router.delete(
    "/complaints/{complaint_id}",
    summary="删除投诉记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.id == complaint_id,
                ComplaintRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        item.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete complaint")
        return error_response(message="删除失败，请稍后重试", status_code=500)
