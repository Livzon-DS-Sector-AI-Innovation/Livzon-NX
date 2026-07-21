"""设备模块飞书 DM 通知 — 使用设备交互机器人凭证发送卡片消息。"""

import json
import logging

logger = logging.getLogger(__name__)


async def send_user_card(
    open_id: str,
    title: str,
    content: str,
    elements: list[dict] | None = None,
    receive_id_type: str = "user_id",
) -> bool:
    """使用设备机器人发送卡片消息给单个用户（DM）。

    Args:
        open_id: 接收者标识（含义由 receive_id_type 决定）
        title: 卡片标题
        content: 卡片正文（支持 markdown）
        elements: 额外的卡片元素
        receive_id_type: 接收者 ID 类型，"user_id" 或 "open_id"

    Returns:
        True 表示发送成功，False 表示失败
    """
    logger.info(
        "设备机器人 send_user_card: %s=%s", receive_id_type, open_id,
    )
    try:
        from app.modules.equipment.feishu.client import (
            get_equipment_feishu_client,
            get_equipment_tenant_token,
        )

        client = await get_equipment_feishu_client()
        token = await get_equipment_tenant_token(client)

        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        card = {
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
                "设备机器人 send_user_card 失败: user_id=%s, code=%s, msg=%s",
                open_id, resp.code, resp.msg,
            )
            return False
        logger.info("设备机器人卡片已发送: user_id=%s, title=%s", open_id, title)
        return True
    except Exception as e:
        logger.error(
            "设备机器人 send_user_card 异常: user_id=%s, %s: %s",
            open_id, type(e).__name__, e,
        )
        return False
