"""质量模块通知设置 API 路由。"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.schemas.notification_settings import (
    QualityNotificationSettingItem,
    UpdateQualityNotificationSettingRequest,
)
from app.modules.quality.service import quality_notification_settings
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/notification-settings",
    summary="获取质量模块通知设置列表",
    response_model=ApiResponseEnvelope[list[QualityNotificationSettingItem]],
)
async def list_quality_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await quality_notification_settings.list_quality_notification_settings(db)
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.put(
    "/notification-settings/{notification_type}",
    summary="保存质量模块通知设置",
    response_model=ApiResponseEnvelope[QualityNotificationSettingItem],
)
async def update_quality_notification_setting(
    notification_type: str,
    data: UpdateQualityNotificationSettingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await quality_notification_settings.update_quality_notification_setting(
        db, notification_type, data
    )
    return success_response(data=result.model_dump(mode="json"))
