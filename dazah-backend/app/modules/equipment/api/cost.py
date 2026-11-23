"""维修成本 API 路由（工单成本补录 + 成本报表）."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.equipment.schemas.purchase_suggestion import (
    WorkOrderExternalCostUpdate,
)
from app.modules.equipment.service import (
    get_cost_report,
    update_external_cost,
)

router = APIRouter()


@router.get("/work-orders/cost-report", summary="维修成本报表")
async def cost_report(
    workshop: str | None = Query(
        None,
        pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
        description="车间代码",
    ),
    month: str | None = Query(
        None, pattern=r"^[0-9]{4}-[0-9]{2}$", description="月份 YYYY-MM"
    ),
    group_by: str = Query(
        "equipment",
        pattern="^(equipment|workshop|fault_type)$",
        description="分组维度",
    ),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    report = await get_cost_report(
        db, workshop_code=workshop, month=month, group_by=group_by
    )
    return success_response(data=report)


@router.put(
    "/work-orders/{work_order_id}/external-cost", summary="补录外委费用"
)
async def set_external_cost(
    work_order_id: uuid.UUID,
    data: WorkOrderExternalCostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    wo = await update_external_cost(
        db,
        work_order_id,
        external_cost=data.external_cost,
        external_vendor=data.external_vendor,
        operator_id=current_user.id,
    )
    return success_response(
        data={
            "id": str(wo.id),
            "external_cost": (
                float(wo.external_cost) if wo.external_cost is not None else None
            ),
            "external_vendor": wo.external_vendor,
        }
    )
