"""Quality module public API for cross-module access."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "get_qa_reminder_recipients",
]


async def get_qa_reminder_recipients(session: AsyncSession) -> list[dict[str, Any]]:
    """QA 通知人候选（证书到期提醒/法规推送）。

    数据源为人事管理-飞书联系人目录，保留"部门含 QA/质量保证"关键字过滤。
    每项包含 open_id/name/department/enterprise_email。
    """
    from app.modules.quality.service.person_directory import (
        get_qa_reminder_recipients as _impl,
    )

    return await _impl(session)
