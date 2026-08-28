"""Project parent aggregate API routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.registration.api._common import require_user as _require_user
from app.modules.registration.schemas import ProjectOverview
from app.modules.registration.service.project import ProjectOverviewService
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/overview",
    summary="获取申报项目总览",
    response_model=ApiResponseEnvelope[ProjectOverview],
)
async def get_project_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await ProjectOverviewService(db).get_overview()
    return success_response(data=overview)
