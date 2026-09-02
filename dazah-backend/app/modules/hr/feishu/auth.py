"""HR 飞书鉴权，仅解析 HR 数据库配置，不回退到登录应用。"""

from app.core.database import async_session_factory
from app.platform.integrations.feishu.auth import FeishuAuth as PlatformFeishuAuth


class FeishuAuth(PlatformFeishuAuth):
    @classmethod
    async def get_tenant_access_token(
        cls, app_id: str | None = None, app_secret: str | None = None
    ) -> str:
        if app_id is None and app_secret is None:
            from app.modules.hr.feishu_settings_service import (
                get_hr_feishu_app_credentials,
            )

            async with async_session_factory() as db:
                app_id, app_secret = await get_hr_feishu_app_credentials(db)
        return await super().get_tenant_access_token(app_id, app_secret)
