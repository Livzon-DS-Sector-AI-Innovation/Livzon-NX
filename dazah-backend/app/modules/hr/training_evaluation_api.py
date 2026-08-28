"""培训评估表 API"""

import logging
from io import BytesIO
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.hr.schemas import (
    TrainingEvaluationCreate,
    TrainingEvaluationResponse,
    TrainingEvaluationUpdate,
)
from app.modules.hr.training_evaluation_service import TrainingEvaluationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training-evaluations", tags=["人事-培训评估表"])


def _require_user(current_user: CurrentUser) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


@router.get("", summary="培训评估表列表")
async def list_evaluations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, description="培训内容搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = TrainingEvaluationService(db)
    evaluations, total = await service.list_evaluations(
        page=page, page_size=page_size, keyword=keyword
    )
    return paginated_response(
        data=[
            TrainingEvaluationResponse.model_validate(e).model_dump(mode="json")
            for e in evaluations
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", summary="创建培训评估表")
async def create_evaluation(
    data: TrainingEvaluationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = TrainingEvaluationService(db)
    evaluation = await service.create(data.model_dump(exclude_unset=True))
    return success_response(
        data=TrainingEvaluationResponse.model_validate(evaluation).model_dump(
            mode="json"
        ),
        message="创建成功",
    )


@router.get("/export/{evaluation_id}", summary="导出培训评估表")
async def export_evaluation(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """导出培训评估表 Word 文档（APP4模板）"""
    _require_user(current_user)
    from app.modules.hr.training_evaluation_document_generator import (
        generate_training_evaluation_doc_from_orm,
    )

    service = TrainingEvaluationService(db)
    evaluation = await service.get_by_id(evaluation_id)
    if not evaluation:
        raise NotFoundException(resource="培训评估表", resource_id=str(evaluation_id))

    buffer: BytesIO = generate_training_evaluation_doc_from_orm(evaluation)
    filename = quote("APP4-SMP-HR-002-14培训评估表.docx")

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{evaluation_id}", summary="培训评估表详情")
async def get_evaluation(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = TrainingEvaluationService(db)
    evaluation = await service.get_by_id(evaluation_id)
    if not evaluation:
        raise NotFoundException(resource="培训评估表", resource_id=str(evaluation_id))
    return success_response(
        data=TrainingEvaluationResponse.model_validate(evaluation).model_dump(
            mode="json"
        )
    )


@router.put("/{evaluation_id}", summary="更新培训评估表")
async def update_evaluation(
    evaluation_id: UUID,
    data: TrainingEvaluationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = TrainingEvaluationService(db)
    evaluation = await service.update(
        evaluation_id, data.model_dump(exclude_unset=True)
    )
    if not evaluation:
        raise NotFoundException(resource="培训评估表", resource_id=str(evaluation_id))
    return success_response(
        data=TrainingEvaluationResponse.model_validate(evaluation).model_dump(
            mode="json"
        ),
        message="更新成功",
    )


@router.delete("/{evaluation_id}", summary="删除培训评估表")
async def delete_evaluation(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = TrainingEvaluationService(db)
    deleted = await service.delete(evaluation_id)
    if not deleted:
        raise NotFoundException(resource="培训评估表", resource_id=str(evaluation_id))
    return success_response(message="删除成功")
