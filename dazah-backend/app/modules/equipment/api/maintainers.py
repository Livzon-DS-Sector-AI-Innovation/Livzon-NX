"""维修人员 API 路由."""

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.equipment import service
from app.modules.equipment.schemas import (
    MaintainerOption,
    UserOption,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/maintainers",
    summary="获取设备模块维修人员列表",
    response_model=ApiResponseEnvelope[list[MaintainerOption]],
)
async def list_maintainers(
    workshop: str | None = Query(
        None, pattern=r"^\d{3}(-\d)?$", description="车间代码（如 101-1 / 201-1）"
    ),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """从人员配置中获取所有在岗人员，供工单指派维修人时选择。"""
    maintainers = await service.list_maintainer_options(db, workshop)
    return success_response(data=maintainers)


@router.get(
    "/all-users",
    summary="获取全体员工列表",
    response_model=ApiResponseEnvelope[list[UserOption]],
)
async def list_all_users(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """返回所有本地用户，供工单责任人选择。"""
    users = await service.list_user_options(db)
    return success_response(data=users)
