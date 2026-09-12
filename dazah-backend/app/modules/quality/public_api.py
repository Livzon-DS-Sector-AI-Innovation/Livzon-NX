"""Quality module public API for cross-module access."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "get_module_feishu_app_credentials",
    "get_qa_reminder_recipients",
]


async def get_module_feishu_app_credentials(session: AsyncSession) -> tuple[str, str]:
    """质量模块飞书应用凭证（app_id, app_secret），供注册域通知借用发送。

    未配置或已停用时返回空字符串对，调用方据此跳过发送。
    """
    from app.modules.quality.feishu_notification import _get_credentials

    return await _get_credentials(session)


async def get_qa_reminder_recipients(session: AsyncSession) -> list[dict[str, Any]]:
    """QA 通知人候选（证书到期提醒/法规推送）。

    数据源为人事管理-飞书联系人目录，保留"部门含 QA/质量保证"关键字过滤。
    每项包含 open_id/name/department/enterprise_email。
    """
    from app.modules.quality.service.person_directory import (
        get_qa_reminder_recipients as _impl,
    )

    return await _impl(session)
