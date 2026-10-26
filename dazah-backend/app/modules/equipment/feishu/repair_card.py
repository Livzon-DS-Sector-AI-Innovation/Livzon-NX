"""维修派单交互卡片：构建、发送与状态更新。

卡片按钮通过长连接 CARD 帧回调（见 ws_client），不依赖公网地址。
凭据使用设备机器人应用（settings.EQUIPMENT_FEISHU_*）。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

FEISHU_DOMAIN = "https://open.feishu.cn"

# tenant_access_token 缓存（进程内，提前 60 秒过期）
_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}

_PRIORITY_STYLE = {
    "紧急": ("red", "🔴 紧急报修"),
    "高": ("orange", "🟠 报修工单"),
    "中": ("blue", "报修工单"),
    "低": ("grey", "报修工单"),
}


async def _tenant_token() -> str:
    """获取（并缓存）设备机器人的 tenant_access_token。"""
    now = time.time()
    cached: str = str(_token_cache["token"])
    if cached and now < float(_token_cache["expires_at"]):
        return cached
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{FEISHU_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.EQUIPMENT_FEISHU_APP_ID,
                "app_secret": settings.EQUIPMENT_FEISHU_APP_SECRET,
            },
        )
        data = resp.json()
    token = str(data.get("tenant_access_token", ""))
    expire = int(data.get("expire", 0) or 1800)
    if not token:
        raise RuntimeError(f"维修机器人 token 获取失败: {data.get('msg')}")
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(expire - 60, 60)
    return token


def _field(label: str, value: str) -> dict[str, Any]:
    return {
        "is_short": True,
        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
    }


def build_dispatch_card(
    *,
    work_order_no: str,
    equipment_label: str,
    workshop_name: str,
    fault: str,
    priority: str,
    reporter_name: str,
) -> dict[str, Any]:
    """待接单派单卡片：接单按钮携带 act/oid，回调直达状态机。"""
    color, title = _PRIORITY_STYLE.get(priority, ("blue", "报修工单"))
    detail_url = (
        f"{settings.FRONTEND_URL}/equipment?module=maintenance"
        if settings.FRONTEND_URL
        else ""
    )
    actions: list[dict[str, Any]] = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "✅ 接单"},
            "type": "primary",
            "value": {"act": "accept", "oid": work_order_no},
        }
    ]
    if detail_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📋 网页处理"},
                "type": "default",
                "url": detail_url,
            }
        )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": color,
            "title": {"tag": "plain_text", "content": f"{title} {work_order_no}"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    _field("设备", equipment_label),
                    _field("车间", workshop_name),
                    _field("报修人", reporter_name),
                    _field("时间", datetime.now(UTC).strftime("%m-%d %H:%M")),
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": fault or "（无描述）"},
            },
            {"tag": "hr"},
            {"tag": "action", "actions": actions},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "点击「接单」立即开始维修；完成后可在此卡片继续提交",
                    }
                ],
            },
        ],
    }


def build_accepted_card(
    *,
    work_order_no: str,
    equipment_label: str,
    assignee_name: str,
    accepted_at: datetime,
) -> dict[str, Any]:
    """已接单卡片：按钮变为「维修完成」。"""
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "green",
            "title": {
                "tag": "plain_text",
                "content": f"✅ 已接单 {work_order_no} · {assignee_name}",
            },
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    _field("设备", equipment_label),
                    _field(
                        "接单时间",
                        accepted_at.astimezone(UTC).strftime("%m-%d %H:%M"),
                    ),
                ],
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🛠 维修完成"},
                        "type": "primary",
                        "value": {"act": "complete", "oid": work_order_no},
                    }
                ],
            },
        ],
    }


def build_completed_card(
    *, work_order_no: str, equipment_label: str, assignee_name: str
) -> dict[str, Any]:
    """已完成待验收卡片。"""
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "template": "turquoise",
            "title": {
                "tag": "plain_text",
                "content": f"🛠 已完成，待验收 {work_order_no}",
            },
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    _field("设备", equipment_label),
                    _field("维修人", assignee_name),
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "请报修人或管理员在平台完成验收"}
                ],
            },
        ],
    }


async def send_card_to_chat(chat_id: str, card: dict[str, Any]) -> str:
    """发送交互卡片到群聊，返回 message_id。"""
    token = await _tenant_token()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{FEISHU_DOMAIN}/open-apis/im/v1/messages"
            "?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
        )
        data = resp.json()
    message_id: str = str((data.get("data") or {}).get("message_id", ""))
    if resp.status_code != 200 or not message_id:
        raise RuntimeError(
            f"派单卡片发送失败: code={data.get('code')}, msg={data.get('msg')}"
        )
    return message_id


async def patch_card_message(message_id: str, card: dict[str, Any]) -> bool:
    """更新原卡片消息（状态演化不刷屏）。"""
    token = await _tenant_token()
    body = json.dumps(card, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{FEISHU_DOMAIN}/open-apis/im/v1/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"content": body},
        )
        data = resp.json()
    logger.debug(
        "卡片PATCH: mid=%s http=%s body=%s resp=%s",
        message_id,
        resp.status_code,
        body[:120],
        json.dumps(data, ensure_ascii=False)[:300],
    )
    if resp.status_code != 200 or data.get("code") != 0:
        logger.warning(
            "卡片更新失败: message_id=%s code=%s msg=%s",
            message_id,
            data.get("code"),
            data.get("msg"),
        )
        return False
    logger.info("卡片更新成功: message_id=%s", message_id)
    return True


async def get_card_title(message_id: str) -> str:
    """查询卡片消息当前标题（GET 返回归一化结构，title 在顶层）。

    用于补丁后复核：飞书在按钮交互窗口期内的 PATCH 可能被静默回滚，
    需以实际内容为准判断是否重打。
    """
    token = await _tenant_token()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{FEISHU_DOMAIN}/open-apis/im/v1/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
        if resp.status_code != 200 or data.get("code") != 0:
            return ""
        items = (data.get("data") or {}).get("items") or []
        content = ""
        if items:
            content = str(((items[0] or {}).get("body") or {}).get("content", ""))
        return str(json.loads(content).get("title", "") or "") if content else ""
    except Exception:
        logger.exception("卡片标题查询失败: message_id=%s", message_id)
        return ""
