"""统计/附件审阅 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.quality import service
from app.modules.quality.api.deps import (
    current_user_id as _current_user_id,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    resolve_quality_list_scope as _resolve_quality_list_scope,
)
from app.modules.quality.schemas import (
    AttachmentReviewOut,
    CapaStatistics,
    ChangeStatistics,
    CreateAttachmentReviewRequest,
    DeviationStatistics,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ Statistics ============


@router.get(
    "/statistics/deviations",
    summary="获取偏差统计",
    response_model=ApiResponseEnvelope[DeviationStatistics],
)
async def get_deviation_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    scope = await _resolve_quality_list_scope(db, current_user)
    stats = await service.get_deviation_statistics(db, scope=scope)
    return success_response(data=stats.model_dump(by_alias=True))


@router.get(
    "/statistics/capas",
    summary="获取CAPA统计",
    response_model=ApiResponseEnvelope[CapaStatistics],
)
async def get_capa_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    scope = await _resolve_quality_list_scope(db, current_user)
    stats = await service.get_capa_statistics(db, scope=scope)
    return success_response(data=stats.model_dump(by_alias=True))


@router.get(
    "/statistics/changes",
    summary="获取变更统计",
    response_model=ApiResponseEnvelope[ChangeStatistics],
)
async def get_change_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    scope = await _resolve_quality_list_scope(db, current_user)
    stats = await service.get_change_statistics(db, scope=scope)
    return success_response(data=stats.model_dump(by_alias=True))


# ============ Attachment Reviews ============


@router.get(
    "/attachment-reviews",
    summary="获取附件审阅列表",
    response_model=ApiResponseEnvelope[list[AttachmentReviewOut]],
)
async def list_attachment_reviews(
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    items = await service.list_attachment_reviews(
        db, deviation_id, capa_id, attachment_url
    )
    return success_response(data=items)


@router.post(
    "/attachment-reviews",
    summary="创建附件审阅",
    response_model=ApiResponseEnvelope[AttachmentReviewOut],
)
async def create_attachment_review(
    data: CreateAttachmentReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_attachment_review(db, data, user_id)
    return success_response(data=result)


@router.delete(
    "/attachment-reviews/{review_id}",
    summary="删除附件审阅",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_attachment_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    await service.delete_attachment_review(db, review_id)
    return success_response(data={"success": True})


# ============ CAPA Import/Export ============
