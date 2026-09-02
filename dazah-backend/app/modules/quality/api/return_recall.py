"""Return & recall API endpoints."""

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
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.return_recall import ReturnRecallRecord
from app.modules.quality.schemas.return_recall import (
    CreateReturnRecallRequest,
    ReturnRecallOut,
    UpdateReturnRecallRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/return-recalls",
    summary="获取退货/召回列表",
    response_model=ApiResponseEnvelope[list[ReturnRecallOut]],
)
async def list_return_recalls(
    record_type: str | None = Query(None, description="记录类型：return/recall"),
    status: str | None = Query(None, description="状态"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(ReturnRecallRecord).where(
            ReturnRecallRecord.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(ReturnRecallRecord)
            .where(ReturnRecallRecord.is_deleted.is_(False))
        )

        filters = []
        if record_type:
            filters.append(ReturnRecallRecord.record_type == record_type)
        if status:
            filters.append(ReturnRecallRecord.status == status)
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters.append(
                or_(
                    ReturnRecallRecord.record_code.ilike(pattern),
                    ReturnRecallRecord.title.ilike(pattern),
                    ReturnRecallRecord.reason.ilike(pattern),
                )
            )

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        base_query = (
            base_query.order_by(ReturnRecallRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items_result = await db.execute(base_query)
        items = items_result.scalars().all()

        return paginated_response(
            data=[
                ReturnRecallOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list return/recall records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.get(
    "/return-recalls/{record_id}",
    summary="获取退货/召回详情",
    response_model=ApiResponseEnvelope[ReturnRecallOut],
)
async def get_return_recall(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ReturnRecallRecord).where(
                ReturnRecallRecord.id == record_id,
                ReturnRecallRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)
        return success_response(
            data=ReturnRecallOut.model_validate(item).model_dump(mode="json")
        )
    except Exception:
        logger.exception("Failed to get return/recall record")
        return error_response(message="获取详情失败，请稍后重试", status_code=500)


@router.post(
    "/return-recalls",
    summary="创建退货/召回记录",
    response_model=ApiResponseEnvelope[ReturnRecallOut],
)
async def create_return_recall(
    data: CreateReturnRecallRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = ReturnRecallRecord(**data.model_dump())
        db.add(record)
        await db.flush()
        result = await db.execute(
            select(ReturnRecallRecord).where(ReturnRecallRecord.id == record.id)
        )
        record = result.scalar_one()
        return success_response(
            data=ReturnRecallOut.model_validate(record).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create return/recall record")
        return error_response(message="创建失败，请稍后重试", status_code=400)


@router.put(
    "/return-recalls/{record_id}",
    summary="更新退货/召回记录",
    response_model=ApiResponseEnvelope[ReturnRecallOut],
)
async def update_return_recall(
    record_id: uuid.UUID,
    data: UpdateReturnRecallRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ReturnRecallRecord).where(
                ReturnRecallRecord.id == record_id,
                ReturnRecallRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        await _assert_quality_edit_scope(db, current_user, record=item)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        result = await db.execute(
            select(ReturnRecallRecord).where(ReturnRecallRecord.id == item.id)
        )
        item = result.scalar_one()
        return success_response(
            data=ReturnRecallOut.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update return/recall record")
        return error_response(message="更新失败，请稍后重试", status_code=400)


@router.delete(
    "/return-recalls/{record_id}",
    summary="删除退货/召回记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_return_recall(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ReturnRecallRecord).where(
                ReturnRecallRecord.id == record_id,
                ReturnRecallRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        await _assert_quality_edit_scope(db, current_user, record=item)

        item.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete return/recall record")
        return error_response(message="删除失败，请稍后重试", status_code=500)
