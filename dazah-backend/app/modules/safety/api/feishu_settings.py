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


@feishu_settings_router.post(
    "/feishu-settings/fire-expiry-notify/test",
    response_model=ApiResponseEnvelope[dict[str, Any]],
    summary="测试消防器材有效期提醒推送发送",
)
async def test_fire_expiry_notify(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[dict[str, Any]]:
    """向已配置的群/个人发送一条样例卡片，验证提醒目标配置。"""
    from app.modules.safety.service import fire_expiry_reminder

    result = await fire_expiry_reminder.send_test_notification(db)
    return ApiResponseEnvelope(data=result)


@feishu_settings_router.post(
    "/feishu-settings/commitment-notify/test",
    response_model=ApiResponseEnvelope[dict[str, Any]],
    summary="测试安全承诺填报推送发送",
)
async def test_commitment_notify(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[dict[str, Any]]:
    """向第一个配置了负责人的车间发送样例填报卡，验证推送通道。"""
    from app.core.exceptions import AppException
    from app.modules.safety.service.commitment_notify import (
        get_commitment_settings,
        send_test_workshop_card,
    )
    from app.modules.safety.service.commitment_workshops import list_configs

    settings = await get_commitment_settings(db)
    if settings is None or not settings.commitment_notify_enabled:
        raise AppException(message="请先启用安全承诺填报推送并保存配置")
    configs = await list_configs(db, ensure=True)
    target = next((c for c in configs if c.reporter_open_id), None)
    if target is None:
        raise AppException(message="请先在车间填报配置中设置至少一个车间的负责人")
    ok = await send_test_workshop_card(
        db, str(target.reporter_open_id), target.workshop_name
    )
    return ApiResponseEnvelope(
        data={
            "success": ok,
            "message": (
                f"测试填报卡已发送给「{target.workshop_name}」负责人，请到飞书查收"
                if ok
                else "测试卡片发送失败，请检查飞书配置与网络"
            ),
        }
    )
