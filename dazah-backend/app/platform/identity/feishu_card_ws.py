"""Livzon assistant Feishu card callback WebSocket client.

This client is only for Livzon assistant interactive card callbacks. It uses
the Livzon assistant Feishu app saved in identity.feishu_configs and keeps the
HTTP callback path available for production deployments with a public URL.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import ssl
import time
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import httpx
import websockets
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.secrets import decrypt_secret
from app.platform.identity.repository import FeishuConfigRepository
from app.platform.identity.service import (
    handle_livzon_feishu_card_action_event,
    handle_livzon_feishu_message_receive_event,
)

logger = logging.getLogger(__name__)

FEISHU_DOMAIN = "https://open.feishu.cn"
WS_ENDPOINT_URL = f"{FEISHU_DOMAIN}/callback/ws/endpoint"

_stop: asyncio.Event | None = None
_ws_task: asyncio.Task[None] | None = None
_ping_interval: int = 120
_last_error: str | None = None
_last_connected_at: float | None = None
_delegated_to_global_ws: bool = False
_background_tasks: set[asyncio.Task[Any]] = set()
_frame_count: dict[str, int] = {
    "received": 0,
    "control": 0,
    "data": 0,
    "event": 0,
    "card_action": 0,
    "im_message": 0,
    "error": 0,
}


async def _active_credentials() -> tuple[str | None, str | None]:
    async with async_session_factory() as db:
        config = await FeishuConfigRepository().get_active(db)
        if config is None:
            settings = get_settings()
            return settings.FEISHU_APP_ID, settings.FEISHU_APP_SECRET
        try:
            app_secret = decrypt_secret(config.encrypted_app_secret)
        except RuntimeError:
            logger.exception("Livzon 助手飞书 App Secret 解密失败，无法启动卡片长连接")
            return None, None
        return config.app_id, app_secret


async def _active_app_id() -> str | None:
    async with async_session_factory() as db:
        config = await FeishuConfigRepository().get_active(db)
        return config.app_id if config is not None else get_settings().FEISHU_APP_ID


async def _uses_global_app_ws() -> bool:
    """Avoid opening two callback connections for the same Feishu app."""
    settings = get_settings()
    if not settings.FEISHU_WS_ENABLED or not settings.FEISHU_APP_ID:
        return False
    return await _active_app_id() == settings.FEISHU_APP_ID


async def _get_ws_url_and_config() -> tuple[str | None, int]:
    app_id, app_secret = await _active_credentials()
    if not app_id or not app_secret:
        return None, 0

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            WS_ENDPOINT_URL,
            json={"AppID": app_id, "AppSecret": app_secret},
        )
    if response.status_code != 200:
        logger.error("Livzon 飞书卡片 WS URL 获取失败 HTTP %s", response.status_code)
        return None, 0

    data = response.json()
    if data.get("code") != 0:
        logger.error(
            "Livzon 飞书卡片 WS URL 获取失败: code=%s msg=%s",
            data.get("code"),
            data.get("msg"),
        )
        return None, 0

    url = data.get("data", {}).get("URL", "")
    query = parse_qs(urlparse(url).query)
    service_id = int(query.get("service_id", ["0"])[0] or 0)

    client_config = data.get("data", {}).get("ClientConfig", {})
    global _ping_interval
    if isinstance(client_config, dict):
        interval = client_config.get("PingInterval", 0)
        if interval > 0:
            _ping_interval = interval

    logger.info(
        "Livzon 飞书卡片 WS URL 获取成功 service_id=%s ping_interval=%s",
        service_id,
        _ping_interval,
    )
    return url, service_id


def _build_ping_frame(service_id: int) -> bytes:
    from lark_oapi.ws.const import HEADER_TYPE  # type: ignore[import-untyped]
    from lark_oapi.ws.enum import FrameType, MessageType  # type: ignore[import-untyped]
    from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]

    frame = Frame()
    header = frame.headers.add()
    header.key = HEADER_TYPE
    header.value = MessageType.PING.value
    frame.service = service_id
    frame.method = FrameType.CONTROL.value
    frame.SeqID = 0
    frame.LogID = 0
    return cast(bytes, frame.SerializeToString())


def _build_ack_frame(frame: Any, payload: dict[str, Any], biz_rt: int) -> bytes:
    from lark_oapi.ws.const import HEADER_BIZ_RT

    header = frame.headers.add()
    header.key = HEADER_BIZ_RT
    header.value = str(biz_rt)
    frame.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return cast(bytes, frame.SerializeToString())


async def _ping_loop(ws: Any, service_id: int) -> None:
    while _stop is not None and not _stop.is_set():
        try:
            await ws.send(_build_ping_frame(service_id))
        except Exception:
            logger.warning("Livzon 飞书卡片 WS PING 失败")
            return
        try:
            await asyncio.wait_for(_stop.wait(), timeout=_ping_interval)
            return
        except TimeoutError:
            pass


def _event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header")
    if isinstance(header, dict):
        event_type = header.get("event_type")
        if isinstance(event_type, str):
            return event_type
    event = payload.get("event")
    if isinstance(event, dict):
        return str(event.get("type") or "")
    return str(payload.get("type") or "")


def _normalize_card_callback_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize identity results to Feishu's v2 callback response schema."""
    normalized: dict[str, Any] = {}
    toast = result.get("toast")
    if isinstance(toast, dict):
        normalized["toast"] = toast

    card = result.get("card")
    if isinstance(card, dict):
        if card.get("type") in {"raw", "template"} and isinstance(
            card.get("data"), dict
        ):
            normalized["card"] = card
        else:
            normalized["card"] = {"type": "raw", "data": card}
    return normalized


async def _handle_card_action_event(payload: dict[str, Any]) -> dict[str, Any]:
    async with async_session_factory() as db:
        try:
            result = await handle_livzon_feishu_card_action_event(db, payload=payload)
            await db.commit()
            return result
        except HTTPException as exc:
            await db.rollback()
            return {
                "toast": {
                    "type": "warning",
                    "content": str(exc.detail),
                }
            }
        except Exception:
            await db.rollback()
            logger.exception("Livzon 飞书卡片动作处理失败")
            return {
                "toast": {
                    "type": "error",
                    "content": "Livzon 助手记录卡片动作失败",
                }
            }


async def _handle_message_receive_event(payload: dict[str, Any]) -> None:
    async with async_session_factory() as db:
        try:
            await handle_livzon_feishu_message_receive_event(db, payload=payload)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Livzon 飞书消息事件处理失败")


async def _dispatch_event(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = _event_type(payload)
    if event_type == "card.action.trigger":
        _frame_count["card_action"] += 1
        result = await _handle_card_action_event(payload)
        callback_result = _normalize_card_callback_result(result)
        card_json = json.dumps(callback_result, ensure_ascii=False)
        return {
            "code": 200,
            "data": base64.b64encode(card_json.encode("utf-8")).decode("ascii"),
        }
    if event_type == "im.message.receive_v1":
        _frame_count["im_message"] += 1
        await _handle_message_receive_event(payload)
    return {"code": 200}


def _immediate_card_ack() -> dict[str, Any]:
    """Build the callback response sent before any database or network work."""
    callback_result = {
        "toast": {
            "type": "info",
            "content": "操作已受理，正在处理",
        }
    }
    card_json = json.dumps(callback_result, ensure_ascii=False)
    return {
        "code": 200,
        "data": base64.b64encode(card_json.encode("utf-8")).decode("ascii"),
    }


async def _process_event_after_ack(payload: dict[str, Any]) -> None:
    event_type = _event_type(payload)
    if event_type == "card.action.trigger":
        result = await _handle_card_action_event(payload)
        # The callback frame has already been acknowledged.  Update the
        # original message through OpenAPI, as required for delayed updates.
        from app.platform.integrations.feishu.event_handler import (
            _update_callback_message,
        )

        await _update_callback_message(result)
    elif event_type == "im.message.receive_v1":
        await _handle_message_receive_event(payload)


def _log_background_completion(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Livzon 飞书事件 ACK 后后台处理失败")


def _schedule_event_after_ack(payload: dict[str, Any]) -> None:
    task = asyncio.create_task(_process_event_after_ack(payload))
    _background_tasks.add(task)
    task.add_done_callback(_log_background_completion)


async def _handle_binary_message(ws: Any, message: bytes) -> None:
    _frame_count["received"] += 1
    start_ms = int(round(time.time() * 1000))
    try:
        from lark_oapi.ws.client import _get_by_key  # type: ignore[import-untyped]
        from lark_oapi.ws.const import HEADER_TYPE
        from lark_oapi.ws.enum import FrameType, MessageType
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame

        frame = Frame()
        frame.ParseFromString(message)
        frame_type = FrameType(frame.method)

        if frame_type == FrameType.CONTROL:
            _frame_count["control"] += 1
            return

        if frame_type != FrameType.DATA:
            return

        _frame_count["data"] += 1
        message_type = MessageType(_get_by_key(frame.headers, HEADER_TYPE))
        should_process_after_ack = False
        if message_type == MessageType.EVENT:
            _frame_count["event"] += 1
            payload = json.loads(frame.payload.decode("utf-8"))
            event_type = _event_type(payload)
            if event_type == "card.action.trigger":
                _frame_count["card_action"] += 1
                ack_payload = _immediate_card_ack()
                should_process_after_ack = True
            elif event_type == "im.message.receive_v1":
                _frame_count["im_message"] += 1
                ack_payload = {"code": 200}
                should_process_after_ack = True
            else:
                ack_payload = {"code": 200}
        else:
            ack_payload = {"code": 200}

        biz_rt = int(round(time.time() * 1000)) - start_ms
        await ws.send(_build_ack_frame(frame, ack_payload, biz_rt))
        if should_process_after_ack:
            _schedule_event_after_ack(payload)
    except Exception as exc:
        _frame_count["error"] += 1
        global _last_error
        _last_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Livzon 飞书卡片 WS 帧处理失败 (%d bytes)", len(message))


async def start_livzon_card_ws() -> None:
    """Start the Livzon assistant Feishu event long connection."""
    settings = get_settings()
    if not (
        settings.LIVZON_FEISHU_EVENT_WS_ENABLED
        or settings.LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED
    ):
        logger.info("Livzon 飞书事件长连接未启用，跳过")
        return

    global _stop, _ws_task, _last_connected_at, _last_error
    global _delegated_to_global_ws
    _stop = asyncio.Event()
    _ws_task = asyncio.current_task()

    if await _uses_global_app_ws():
        _delegated_to_global_ws = True
        _last_error = None
        logger.info(
            "Livzon 助手与全局飞书使用同一应用，复用平台长连接，"
            "不再启动重复回调连接"
        )
        return

    _delegated_to_global_ws = False
    logger.info("启动 Livzon 助手飞书事件长连接")

    while _stop is not None and not _stop.is_set():
        try:
            ws_url, service_id = await _get_ws_url_and_config()
            if not ws_url:
                _last_error = "Livzon 助手飞书配置缺失或无法获取 WS URL"
                await asyncio.wait_for(_stop.wait(), timeout=15)
                continue

            ssl_context = ssl.create_default_context()
            async with websockets.connect(
                ws_url,
                ssl=ssl_context,
                max_size=2**23,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
            ) as ws:
                _last_error = None
                _last_connected_at = time.time()
                logger.info("Livzon 助手飞书事件长连接已连接")
                ping_task = asyncio.create_task(_ping_loop(ws, service_id))
                try:
                    while _stop is not None and not _stop.is_set():
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=180)
                        except TimeoutError:
                            continue
                        if isinstance(message, bytes):
                            await _handle_binary_message(ws, message)
                finally:
                    ping_task.cancel()
        except asyncio.CancelledError:
            break
        except websockets.exceptions.ConnectionClosed as exc:
            _last_error = f"ConnectionClosed: {exc}"
            logger.warning("Livzon 飞书卡片长连接关闭，5 秒后重连: %s", exc)
        except TimeoutError:
            continue
        except Exception as exc:
            _last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Livzon 飞书卡片长连接异常，10 秒后重连")

        try:
            await asyncio.wait_for(_stop.wait(), timeout=10)
        except TimeoutError:
            pass

    logger.info("Livzon 助手飞书事件长连接已停止")


async def stop_livzon_card_ws() -> None:
    global _stop, _delegated_to_global_ws
    _delegated_to_global_ws = False
    if _stop is not None:
        _stop.set()


async def restart_livzon_card_ws() -> dict[str, Any]:
    global _ws_task
    await stop_livzon_card_ws()
    if _ws_task and not _ws_task.done():
        _ws_task.cancel()
        try:
            await _ws_task
        except asyncio.CancelledError:
            pass
    _ws_task = asyncio.create_task(start_livzon_card_ws())
    return await get_livzon_card_ws_status()


async def get_livzon_card_ws_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": (
            settings.LIVZON_FEISHU_EVENT_WS_ENABLED
            or settings.LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED
        ),
        "event_ws_enabled": settings.LIVZON_FEISHU_EVENT_WS_ENABLED,
        "legacy_card_callback_ws_enabled": (
            settings.LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED
        ),
        "running": _delegated_to_global_ws
        or (_ws_task is not None and not _ws_task.done()),
        "last_connected_at": _last_connected_at,
        "last_error": _last_error,
        "ping_interval": _ping_interval,
        "frames": dict(_frame_count),
        "event_types": ["im.message.receive_v1", "card.action.trigger"],
    }
