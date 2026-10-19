"""Quality module public API for cross-module access."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "convert_word_attachment_text",
    "get_module_feishu_app_credentials",
    "get_qa_reminder_recipients",
]


def convert_word_attachment_text(file_name: str, content: bytes) -> str:
    """word（.doc/.docx/.wps）→ 文本（标准 MD），供跨模块文档解析兜底。

    与文件管理附件同一条转换管线：OOXML 直析 → LibreOffice headless 转
    .docx → catdoc/antiword 文本兜底；全部失败抛 AppException。
    阻塞调用（含 soffice 子进程），调用方须放线程执行。图片不返回。
    """
    from app.modules.quality.service.document_catalog_md import (
        convert_word_attachment,
    )

    text, _images = convert_word_attachment(file_name, content)
    return text


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
