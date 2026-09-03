"""设备模块群通知，仅使用设备应用配置。"""

import logging
from typing import Any

from app.core.config import get_settings
from app.platform.integrations.feishu.message import send_group_card as _send_group_card

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_group_card(
    chat_id: str, title: str, content: str, elements: list[dict[str, Any]] | None = None
) -> bool:
    return await _send_group_card(
        chat_id,
        title,
        content,
        elements,
        app_id=settings.EQUIPMENT_FEISHU_APP_ID,
        app_secret=settings.EQUIPMENT_FEISHU_APP_SECRET,
    )


async def send_work_order_card(
    work_order_no: str,
    equipment_name: str,
    fault_description: str,
    priority: str,
    reporter_name: str,
    claim_url: str,
) -> bool:
    """发送工单通知卡片到设备部群聊"""
    chat_id = settings.FEISHU_EQUIPMENT_CHAT_ID
    if not chat_id:
        logger.warning("FEISHU_EQUIPMENT_CHAT_ID not configured, skip push")
        return False

    title = f"🔧 新维修工单 {work_order_no}"
    content = (
        f"**设备：**{equipment_name}\n"
        f"**优先级：**{priority}\n"
        f"**报修人：**{reporter_name}\n"
        f"**描述：**{fault_description or '（无）'}"
    )
    elements = [
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "立即抢单"},
                    "type": "primary",
                    "url": claim_url,
                },
            ],
        },
    ]

    return await send_group_card(chat_id, title, content, elements)


async def send_claim_notification(work_order_no: str, claimer_name: str) -> bool:
    """工单被抢后通知群聊"""
    chat_id = settings.FEISHU_EQUIPMENT_CHAT_ID
    if not chat_id:
        return False

    return await send_group_card(
        chat_id,
        title="✅ 工单已被接单",
        content=f"**{claimer_name}** 已接单 **{work_order_no}**",
    )


async def send_timeout_notification(
    work_order_no: str, equipment_name: str, leader_name: str
) -> bool:
    """超时未接单通知主管"""
    chat_id = settings.FEISHU_EQUIPMENT_CHAT_ID
    if not chat_id:
        return False

    return await send_group_card(
        chat_id,
        title="⏰ 工单超时未接单",
        content=(
            f"**{work_order_no}**（{equipment_name}）超时无人接单\n"
            f"请主管 **{leader_name}** 及时派发"
        ),
    )
