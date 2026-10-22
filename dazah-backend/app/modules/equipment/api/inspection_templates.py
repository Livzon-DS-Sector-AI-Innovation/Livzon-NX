"""工单巡检结果提交 API（旧模板 CRUD 已随本地巡检旧轨下线）.

模板与检查项数据仍由飞书机器人和存量数据使用，仅保留工单巡检结果的
提交入口；模板管理不再提供 HTTP 界面。
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.equipment import service
from app.modules.equipment.schemas import (
    InspectionCompleteRequest,
    WorkOrderResponse,
)
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()


@router.post(
    "/complete/{work_order_id}",
    summary="提交巡检结果",
    response_model=ApiResponseEnvelope[WorkOrderResponse],
)
async def complete_inspection(
    work_order_id: uuid.UUID,
    data: InspectionCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    wo = await service.complete_inspection(db, work_order_id, data)
    return success_response(data=WorkOrderResponse.model_validate(wo))
