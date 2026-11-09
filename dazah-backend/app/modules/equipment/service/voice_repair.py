"""语音报修（方案E）：语音消息 → 飞书 ASR 转文字 → 复用文字报修链路。

设计约束：
- ASR 走飞书自建应用凭据（应用库/环境配置），未配置或失败一律回落
  文字引导，语音链路可用性不依赖 ASR 在线；
- 限流每人每分钟 3 条（复用拍照报修的 Redis 计数模式）。
"""

from __future__ import annotations

import json
import logging

from app.modules.equipment.feishu.notification import send_user_card

logger = logging.getLogger(__name__)

_VOICE_RATE_LIMIT = 3
_VOICE_RATE_WINDOW = 60


async def process_voice_repair(
    *,
    user_id: str,
    open_id: str,
    union_id: str,
    message_id: str,
    content: str,
) -> None:
    """处理私聊语音消息：限流 → 下载 → ASR → 文字报修链路。"""
    try:
        from app.core.redis import redis_client

        rate_key = f"repair:voice:rate:{open_id}"
        count = await redis_client.incr(rate_key)
        if count == 1:
            await redis_client.expire(rate_key, _VOICE_RATE_WINDOW)
        if count > _VOICE_RATE_LIMIT:
            await send_user_card(
                open_id=open_id,
                title="⏳ 语音报修太频繁",
                receive_id_type="open_id",
                content="语音消息较多，请稍后再试；或直接发送文字「报修 …」。",
            )
            return

        try:
            content_data = json.loads(content)
            file_key = content_data.get("file_key", "")
        except (json.JSONDecodeError, TypeError):
            file_key = ""

        if not file_key:
            await _fallback(open_id, "语音文件读取失败")
            return

        audio = await _download_voice(message_id, file_key)
        if audio is None:
            await _fallback(open_id, "语音文件下载失败")
            return

        text = await _speech_to_text(audio)
        if not text:
            await _fallback(open_id, "语音未能识别出内容")
            return

        text = text.strip()
        if not text.startswith("报修"):
            text = f"报修 {text}"

        await send_user_card(
            open_id=open_id,
            title="🎙 语音已识别",
            receive_id_type="open_id",
            content=f"识别结果：`{text[:80]}`\n\n正在按文字报修处理…",
        )
        from app.modules.equipment.service.work_order_feishu import (
            create_repair_by_text,
        )

        await create_repair_by_text(
            user_id=user_id, open_id=open_id, text=text, union_id=union_id
        )
    except Exception:
        logger.exception("语音报修处理失败: %s", message_id)
        await _fallback(open_id, "语音处理异常")


async def _download_voice(message_id: str, file_key: str) -> bytes | None:
    """下载语音文件（复用飞书消息资源接口，type=file）。"""
    try:
        from lark_oapi.api.im.v1.model.get_message_resource_request import (  # type: ignore[import-untyped]
            GetMessageResourceRequest,
        )

        from app.modules.equipment.feishu.client import (
            get_equipment_feishu_client,
            get_equipment_tenant_token,
        )

        client = await get_equipment_feishu_client()
        token = await get_equipment_tenant_token(client)
        req = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type("file")
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.im.v1.message_resource.aget(req)
        if resp.code == 0 and resp.file:
            data: bytes = resp.file.read()
            return data
        logger.warning("语音下载失败: code=%s msg=%s", resp.code, resp.msg)
        return None
    except Exception:
        logger.warning("语音下载失败: %s/%s", message_id, file_key, exc_info=True)
        return None


async def _speech_to_text(audio: bytes) -> str | None:
    """飞书语音转文字（speech_to_text v1）；失败返回 None（回落文字引导）。

    需应用开通「语音转文字」权限；未开通时此接口报错，语音链路自动回落。
    """
    try:

        from app.modules.equipment.feishu.client import (
            get_equipment_feishu_client,
            get_equipment_tenant_token,
        )

        client = await get_equipment_feishu_client()
        token = await get_equipment_tenant_token(client)

        import httpx

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://open.feishu.cn/open-apis/speech_to_text/v1/speech_to_text",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "audio/opus",
                },
                content=audio,
            )
        if resp.status_code != 200:
            logger.info("ASR HTTP %s，回落", resp.status_code)
            return None
        data = resp.json()
        if data.get("code") != 0:
            logger.info("ASR code=%s，回落", data.get("code"))
            return None
        # 兼容 data.data.text / data.text 两种返回形态
        payload = data.get("data") or {}
        text = payload.get("text") or data.get("text") or ""
        return (text or "").strip() or None
    except Exception:
        logger.info("语音 ASR 未生效（未配置或不支持），回落文字引导",
                    exc_info=True)
        return None


async def _fallback(open_id: str, reason: str) -> None:
    try:
        await send_user_card(
            open_id=open_id,
            title="🎙 语音报修暂不可用",
            receive_id_type="open_id",
            content=(
                f"{reason}。\n\n请直接发送文字报修：\n"
                "`报修 201一车间 离心泵 密封漏了 紧急`\n"
                "或发送「再报」快捷再报上次那台设备。"
            ),
        )
    except Exception:
        logger.exception("语音回落提示发送失败")
