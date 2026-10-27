"""Safety API — 总览驾驶舱聚合端点。

厂区平面图当日风险落点、超储物料 Top 与近 7 日作业类型统计；
仅模块级查看权限，不绑定具体页面。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.modules.safety.schemas.dashboard import SafetyOverviewResponse
from app.modules.safety.service.dashboard import SafetyOverviewService
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
