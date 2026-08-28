"""岗位培训映射 API."""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import success_response
from app.modules.hr.position_training_mapping_service import (
    PositionTrainingMappingService,
)
from app.modules.hr.schemas import (
    PositionTrainingMappingCreate,
    PositionTrainingMappingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/position-training-mappings", tags=["人事-岗位映射"])


def _require_user(current_user: CurrentUser) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


def _get_service(db: AsyncSession = Depends(get_db)) -> PositionTrainingMappingService:
    return PositionTrainingMappingService(db)


@router.get("", summary="查询岗位映射列表")
async def list_mappings(
    department: str = Query(..., description="部门"),
    db: AsyncSession = Depends(get_db),
    service: PositionTrainingMappingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    mappings = await service.list_mappings(department)
    data = [
        PositionTrainingMappingResponse.model_validate(m).model_dump(mode="json")
        for m in mappings
    ]
    return success_response(data=data)


@router.post("", summary="创建岗位映射")
async def create_mapping(
    body: PositionTrainingMappingCreate,
    db: AsyncSession = Depends(get_db),
    service: PositionTrainingMappingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    mapping = await service.create_mapping(body, user_id)
    return success_response(
        data=PositionTrainingMappingResponse.model_validate(mapping).model_dump(
            mode="json"
        ),
        message="岗位映射已保存",
    )


@router.delete("/{mapping_id}", summary="删除岗位映射")
async def delete_mapping(
    mapping_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: PositionTrainingMappingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    deleted = await service.delete_mapping(mapping_id)
    if not deleted:
        raise NotFoundException(resource="岗位映射", resource_id=str(mapping_id))
    return success_response(message="已删除")
