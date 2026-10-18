"""Safety API — 飞书应用设置端点。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.modules.safety.schemas.feishu_settings import (
    SafetyFeishuAppSettingsDetail,
    SafetyFeishuSettingsTestResult,
    UpdateSafetyFeishuAppSettingsRequest,
)
from app.modules.safety.service import feishu_settings
from app.shared.schemas import ApiResponseEnvelope

feishu_settings_router = APIRouter()


@feishu_settings_router.get(
    "/feishu-settings/app",
    response_model=ApiResponseEnvelope[SafetyFeishuAppSettingsDetail],
    summary="获取安全模块飞书应用配置",
)
async def get_safety_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFeishuAppSettingsDetail]:
    """返回当前配置（App Secret 仅掩码回显）。"""
    result = await feishu_settings.get_safety_feishu_app_settings(db)
    return ApiResponseEnvelope(data=result)


@feishu_settings_router.put(
    "/feishu-settings/app",
    response_model=ApiResponseEnvelope[SafetyFeishuAppSettingsDetail],
    summary="保存安全模块飞书应用配置",
)
async def save_safety_feishu_app_settings(
    data: UpdateSafetyFeishuAppSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFeishuAppSettingsDetail]:
    """保存应用凭证与隐患多维表格绑定；Secret 加密存储。"""
    result = await feishu_settings.update_safety_feishu_app_settings(db, data)
    return ApiResponseEnvelope(data=result)


@feishu_settings_router.post(
    "/feishu-settings/app/test",
    response_model=ApiResponseEnvelope[SafetyFeishuSettingsTestResult],
    summary="测试安全模块飞书应用连接",
)
async def test_safety_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFeishuSettingsTestResult]:
    """用已保存凭证换取 tenant_access_token 验证连通性并记录结果。"""
    result = await feishu_settings.test_safety_feishu_app_settings(db)
    return ApiResponseEnvelope(data=result)


@feishu_settings_router.post(
    "/feishu-settings/hazard-due-notify/test",
    response_model=ApiResponseEnvelope[dict[str, Any]],
    summary="测试隐患到期提醒推送发送",
)
async def test_hazard_due_notify(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[dict[str, Any]]:
    """向已配置的群/个人发送一条样例卡片，验证提醒目标配置。"""
    from app.modules.safety.service import hazard_due_reminder

    result = await hazard_due_reminder.send_test_notification(db)
    return ApiResponseEnvelope(data=result)
