"""无业务归属的飞书群卡片发送。调用方必须提供应用凭证。"""

from typing import Any

from app.platform.integrations.feishu.notification import send_user_card


async def send_group_card(
    chat_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
    *,
    app_id: str = "",
    app_secret: str = "",
) -> bool:
    return await send_user_card(
        chat_id,
        title,
        content,
        elements,
        receive_id_type="chat_id",
        app_id=app_id,
        app_secret=app_secret,
    )
