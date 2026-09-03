"""通用飞书通知服务。

提供可被任何业务模块调用的飞书消息发送能力：
- send_user_card: 发送卡片消息给单个用户（DM）
- 自动管理 tenant access token 生命周期

群聊消息发送请使用同目录下 message.py 中的 send_group_card。
"""

import json
import logging
from typing import Any

from app.platform.integrations.feishu.auth import (
    FeishuAuth,
    FeishuCredentialsRequiredError,
)

logger = logging.getLogger(__name__)


async def _get_client(app_id: str, app_secret: str) -> Any:
    """获取 lark-oapi 客户端实例"""
    if not app_id or not app_secret:
        raise FeishuCredentialsRequiredError()
    import lark_oapi as lark  # type: ignore[import-untyped]

    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .timeout(15.0)
        .domain(lark.FEISHU_DOMAIN)
        .app_type(lark.AppType.SELF)
        .build()
    )


async def _get_tenant_token(app_id: str, app_secret: str) -> str:
    return await FeishuAuth.get_tenant_access_token(app_id, app_secret)


async def send_user_card(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
    receive_id_type: str = "open_id",
    *,
    app_id: str = "",
    app_secret: str = "",
) -> bool:
    """发送卡片消息给单个用户（DM）。

    Args:
        open_id: 飞书 open_id（应用维度的用户标识，如 "ou_xxx"）
        title: 卡片标题
        content: 卡片正文（支持 markdown）
        elements: 额外的卡片元素（按钮、分割线等）

    Returns:
        True 表示发送成功，False 表示失败（不抛异常）
    """
    logger.info("send_user_card: attempting to send to open_id=%s", open_id)
    try:
        client = await _get_client(app_id, app_secret)
        token = await _get_tenant_token(app_id, app_secret)

        from lark_oapi.api.im.v1 import (  # type: ignore[import-untyped]
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        card: dict[str, Any] = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "orange",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        }
        if elements:
            card["elements"].extend(elements)

        card_json = json.dumps(card, ensure_ascii=False)
        logger.info("send_user_card: card JSON length=%d", len(card_json))

        req = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(open_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.im.v1.message.acreate(req)
        if not resp.success():
            logger.error(
                "❌ send_user_card FAILED: open_id=%s, code=%s, status_code=%s",
                open_id,
                resp.code,
                resp.status_code if hasattr(resp, "status_code") else "N/A",
            )
            return False
        logger.info("✅ Card sent to open_id=%s: %s", open_id, title)
        return True
    except Exception as e:
        logger.error(
            "❌ send_user_card EXCEPTION for open_id=%s: %s",
            open_id,
            type(e).__name__,
        )
        return False


async def send_user_card_with_message_id(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict[str, Any]] | None = None,
    receive_id_type: str = "open_id",
    *,
    app_id: str = "",
    app_secret: str = "",
) -> str | None:
    """Send a card and return Feishu's message id when available.

    Requires explicit business credentials; never uses the login application.
    """
    logger.info("send_user_card_with_message_id: attempting to send to %s", open_id)
    try:
        client = await _get_client(app_id, app_secret)
        token = await _get_tenant_token(app_id, app_secret)

        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        card_json = await build_card(title=title, content=content, elements=elements)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(open_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        request.headers["Authorization"] = f"Bearer {token}"
        response = await client.im.v1.message.acreate(request)
        if not response.success():
            logger.error(
                "send_user_card_with_message_id failed: code=%s",
                response.code,
            )
            return None
        return response.data.message_id if response.data else None
    except Exception as exc:
        logger.error("send_user_card_with_message_id failed: %s", type(exc).__name__)
        return None


async def build_card(
    title: str,
    content: str,
    header_template: str = "orange",
    elements: list[dict[str, Any]] | None = None,
) -> str:
    """构建飞书卡片 JSON 字符串。

    业务模块可用此函数构建卡片，然后自行调用发送。

    Args:
        title: 卡片标题
        content: markdown 正文
        header_template: 标题颜色模板（orange/blue/green/red/purple）
        elements: 额外元素列表

    Returns:
        飞书卡片 JSON 字符串
    """
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": header_template,
        },
        "elements": [
            {"tag": "markdown", "content": content},
        ],
    }
    if elements:
        card["elements"].extend(elements)
    return json.dumps(card, ensure_ascii=False)


async def update_card(
    message_id: str, card: dict[str, Any], *, app_id: str = "", app_secret: str = ""
) -> bool:
    """Update an existing Feishu interactive card."""
    logger.info("update_card: attempting to patch message_id=%s", message_id)
    try:
        client = await _get_client(app_id, app_secret)
        token = await _get_tenant_token(app_id, app_secret)

        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        request.headers["Authorization"] = f"Bearer {token}"
        response = await client.im.v1.message.apatch(request)
        if not response.success():
            logger.error("update_card failed: code=%s", response.code)
            return False
        return True
    except Exception as exc:
        logger.error("update_card failed: %s", type(exc).__name__)
        return False
