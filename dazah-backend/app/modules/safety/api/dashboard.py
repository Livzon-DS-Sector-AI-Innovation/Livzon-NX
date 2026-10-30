"""Safety API — 总览驾驶舱聚合端点。

厂区平面图当日风险落点、超储物料 Top 与近 7 日作业类型统计；
仅模块级查看权限，不绑定具体页面。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.modules.safety.schemas.dashboard import (
    OpenHazardDetailItem,
    SafetyOverviewResponse,
)
from app.modules.safety.service.dashboard import (
    SafetyOverviewService,
    list_open_hazard_details,
)
from app.shared.schemas import ApiResponseEnvelope

safety_dashboard_router = APIRouter()


@safety_dashboard_router.get(
    "/dashboard/overview",
    response_model=ApiResponseEnvelope[SafetyOverviewResponse],
    summary="安全总览驾驶舱聚合（建筑底册 + 当日落点 + 超储 + 近7日统计）",
)
async def get_safety_overview(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyOverviewResponse]:
    service = SafetyOverviewService(db)
    return ApiResponseEnvelope(data=await service.get_overview())


@safety_dashboard_router.get(
    "/open-hazard-details",
    response_model=ApiResponseEnvelope[list[OpenHazardDetailItem]],
    summary="未关闭隐患明细（来源：24小时值班隐患 / 隐患台账）",
)
async def get_open_hazard_details(
    source: str = Query(..., description="来源: duty=24小时值班隐患 / ledger=隐患台账"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[OpenHazardDetailItem]]:
    return ApiResponseEnvelope(
        data=await list_open_hazard_details(db, source=source, limit=limit)
    )

