"""模块飞书通知：使用模块配置，不使用登录应用凭证。"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.platform.identity.public_api import resolve_feishu_notification_recipient
from app.platform.integrations.feishu import notification
from app.platform.integrations.feishu.notification import build_card as build_card

logger = logging.getLogger(__name__)


async def _get_credentials(db: AsyncSession) -> tuple[str, str]:
    from app.core.llm.encryption import decrypt_api_key
    from app.modules.quality.service.quality_feishu_settings import (
        _get_app_settings_model,
    )

    model = await _get_app_settings_model(db)
    if model is None or not model.is_enabled or model.is_deleted:
        return "", ""
    return model.app_id or "", decrypt_api_key(
        model.app_secret
    ) if model.app_secret else ""


async def send_user_card_with_message_id(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
    receive_id_type: str = "open_id",
) -> str | None:
    try:
        async with async_session_factory() as db:
            app_id, app_secret = await _get_credentials(db)
            if not app_id or not app_secret:
                logger.warning("模块飞书通知未配置或已停用，跳过发送")
                return None
            recipient = await resolve_feishu_notification_recipient(
                db, open_id, receive_id_type
            )
        if recipient is None:
            logger.warning("通知接收人缺少跨应用用户标识，跳过发送")
            return None
        return await notification.send_user_card_with_message_id(
            recipient[0],
            title,
            content,
            elements,
            recipient[1],
            app_id=app_id,
            app_secret=app_secret,
        )
    except Exception as exc:
        logger.error("模块飞书通知失败：%s", type(exc).__name__)
        return None


async def send_user_card(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
    receive_id_type: str = "open_id",
) -> bool:
    return bool(
        await send_user_card_with_message_id(
            open_id, title, content, elements, receive_id_type
        )
    )


async def update_card(message_id: str, card: dict[str, Any]) -> bool:
    try:
        async with async_session_factory() as db:
            app_id, app_secret = await _get_credentials(db)
        return await notification.update_card(
            message_id, card, app_id=app_id, app_secret=app_secret
        )
    except Exception as exc:
        logger.error("模块飞书卡片更新失败：%s", type(exc).__name__)
        return False
