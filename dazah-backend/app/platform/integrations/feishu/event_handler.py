"""飞书事件处理器 — 全局飞书应用。

事件处理器在 WebSocket 线程中同步调用，
通过 asyncio.run_coroutine_threadsafe 桥接到主 async event loop。

注意：设备模块巡检交互已迁移到独立的设备交互机器人，
见 app/modules/equipment/feishu/handler.py。
"""

import asyncio
import json
import logging
from concurrent.futures import Future

import lark_oapi as lark
from lark_oapi.api.drive.v1 import P2DriveFileBitableRecordChangedV1
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from app.core.events import event_bus
from app.platform.integrations.feishu.utils import FEISHU_BITABLE_RECORD_CHANGED_EVENT

logger = logging.getLogger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """设置主 event loop 引用，供异步桥接使用。"""
    global _main_loop
    _main_loop = loop


def build_event_handler() -> lark.EventDispatcherHandler:
    """构建飞书事件处理器，注册所有事件监听。"""
    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_receive)
        .register_p2_card_action_trigger(_on_card_action_trigger)
        .register_p2_drive_file_bitable_record_changed_v1(
            _on_bitable_record_changed
        )
        .build()
    )


def _on_message_receive(data: P2ImMessageReceiveV1) -> None:
    """消息接收事件处理（同步入口，在 WS 线程中调用）。"""
    event = data.event
    if not event or not event.message:
        return

    message = event.message
    sender = event.sender
    msg_type = message.message_type
    message_id = message.message_id
    chat_type = message.chat_type or ""
    sender_id = ""
    sender_type = ""

    if sender and sender.sender_id:
        sender_id = sender.sender_id.open_id or ""
    if sender:
        sender_type = sender.sender_type or ""

    logger.info(
        "全局飞书收到消息: type=%s, sender=%s, chat_type=%s, message_id=%s",
        msg_type, sender_id, chat_type, message_id,
    )

    if _main_loop is None:
        logger.error("主 event loop 未设置，无法处理消息")
        return

    future = asyncio.run_coroutine_threadsafe(
        _handle_message_async(
            msg_type=msg_type,
            message_id=message_id,
            content=message.content or "{}",
            chat_type=chat_type,
            sender_open_id=sender_id,
            sender_type=sender_type,
        ),
        _main_loop,
    )
    future.add_done_callback(_log_message_completion)


def _log_message_completion(future: Future) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("飞书消息后台处理异常")


def _card_callback_response(
    *,
    toast_type: str,
    content: str,
) -> P2CardActionTriggerResponse:
    return P2CardActionTriggerResponse(
        {"toast": {"type": toast_type, "content": content}}
    )


def _on_card_action_trigger(
    data: P2CardActionTrigger,
) -> P2CardActionTriggerResponse:
    """Handle a Livzon card callback received by the shared global client.

    Feishu randomly assigns a shared application's long-connection callbacks
    to one client.  The Livzon raw connection already handles card callbacks,
    but the platform SDK connection must handle them too when both use the
    same App ID; otherwise a click routed to this client returns a 500/error.
    """
    if _main_loop is None:
        logger.error("主 event loop 未设置，无法处理飞书卡片回调")
        return _card_callback_response(
            toast_type="error",
            content="Livzon 助手暂时不可用，请稍后重试",
        )

    try:
        payload = json.loads(lark.JSON.marshal(data))
    except (TypeError, ValueError):
        logger.exception("全局飞书卡片回调序列化失败")
        return _card_callback_response(
            toast_type="error",
            content="卡片回调格式无效",
        )

    future = asyncio.run_coroutine_threadsafe(
        _handle_card_action_async(payload),
        _main_loop,
    )
    future.add_done_callback(_log_card_action_completion)

    # Feishu starts its three-second deadline when the frame reaches the SDK,
    # not when this handler starts running.  A shared connection can still be
    # draining message events, so waiting for database and downstream network
    # work here causes an otherwise successful action to be retried.  ACK the
    # click immediately and finish the audited operation on the main loop.
    return _card_callback_response(
        toast_type="info",
        content="操作已受理，正在处理",
    )


def _log_card_action_completion(future: Future) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("共享飞书应用卡片动作后台处理异常")


def _event_id(payload: dict) -> str | None:
    header = payload.get("header")
    if isinstance(header, dict) and isinstance(header.get("event_id"), str):
        return header["event_id"]
    return None


async def _handle_message_async(
    *,
    msg_type: str,
    message_id: str,
    content: str,
    chat_type: str,
    sender_open_id: str,
    sender_type: str,
) -> None:
    """异步处理消息（在主 event loop 中运行）。"""
    if _main_loop is None:
        set_main_loop(asyncio.get_running_loop())

    # 消息去重
    from app.core.redis import redis_client

    dedup_key = f"feishu:msg:{message_id}"
    is_new = await redis_client.set(dedup_key, "1", ex=120, nx=True)
    if not is_new:
        logger.info("重复消息已忽略: message_id=%s", message_id)
        return

    if await _uses_shared_livzon_app():
        await _forward_shared_app_message_to_livzon(
            msg_type=msg_type,
            message_id=message_id,
            content=content,
            chat_type=chat_type,
            sender_open_id=sender_open_id,
            sender_type=sender_type,
        )
        return

    logger.info("全局飞书消息已记录: type=%s, message_id=%s", msg_type, message_id)


async def _handle_card_action_async(payload: dict) -> dict:
    """Dispatch a shared application's card callback into the Livzon boundary."""
    if not await _uses_shared_livzon_app():
        return {
            "toast": {
                "type": "warning",
                "content": "该卡片不属于 Livzon 助手",
            }
        }

    from fastapi import HTTPException

    from app.core.database import async_session_factory
    from app.platform.identity.service import handle_livzon_feishu_card_action_event

    async with async_session_factory() as db:
        try:
            result = await handle_livzon_feishu_card_action_event(db, payload=payload)
            await db.commit()
            await _update_callback_message(result)
            logger.info(
                "共享飞书应用卡片动作已转交 Livzon: event_id=%s toast_type=%s",
                _event_id(payload),
                (result.get("toast") or {}).get("type")
                if isinstance(result, dict)
                else "unknown",
            )
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
            logger.exception(
                "共享飞书应用卡片动作转交 Livzon 失败: event_id=%s",
                _event_id(payload),
            )
            return {
                "toast": {
                    "type": "error",
                    "content": "Livzon 助手记录卡片动作失败",
                }
            }


async def _update_callback_message(result: dict) -> None:
    """Replace the original card after the immediate callback ACK."""
    message_id = result.get("_callback_message_id")
    card = result.get("card")
    if not isinstance(message_id, str) or not message_id or not isinstance(card, dict):
        return

    from app.core.config import get_settings
    from app.platform.integrations.feishu.im import update_feishu_message
    from app.platform.integrations.feishu.utils import get_tenant_access_token

    settings = get_settings()
    try:
        token = await get_tenant_access_token(
            settings.FEISHU_APP_ID,
            settings.FEISHU_APP_SECRET,
            cache_key=f"shared-callback:{settings.FEISHU_APP_ID}",
        )
        updated = await update_feishu_message(
            tenant_access_token=token,
            message_id=message_id,
            content=json.dumps(card, ensure_ascii=False),
        )
        if not updated.ok:
            logger.warning(
                "飞书确认卡片异步更新失败: message_id=%s code=%s",
                message_id,
                updated.code,
            )
    except Exception:
        logger.exception("飞书确认卡片异步更新异常: message_id=%s", message_id)


async def _uses_shared_livzon_app() -> bool:
    """Whether the global event app is also the configured Livzon app.

    The project keeps the platform-wide long connection for Bitable and other
    platform events. When that application is also Livzon, Feishu can deliver
    a private message to this SDK connection instead of Livzon's raw client.
    Route only that shared-app case into the Livzon boundary.
    """
    from app.core.config import get_settings
    from app.core.database import async_session_factory
    from app.platform.identity.repository import FeishuConfigRepository

    global_app_id = get_settings().FEISHU_APP_ID
    if not global_app_id:
        return False
    async with async_session_factory() as db:
        config = await FeishuConfigRepository().get_active(db)
    return bool(config and config.app_id == global_app_id)


async def _forward_shared_app_message_to_livzon(
    *,
    msg_type: str,
    message_id: str,
    content: str,
    chat_type: str,
    sender_open_id: str,
    sender_type: str,
) -> None:
    """Use the identity-owned Livzon entrypoint for a shared application."""
    from app.core.database import async_session_factory
    from app.platform.identity.service import handle_livzon_feishu_message_receive_event

    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_type": sender_type,
                "sender_id": {"open_id": sender_open_id},
            },
            "message": {
                "message_type": msg_type,
                "message_id": message_id,
                "chat_type": chat_type,
                "content": content,
            },
        },
    }
    async with async_session_factory() as db:
        try:
            result = await handle_livzon_feishu_message_receive_event(
                db, payload=payload
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "共享飞书应用消息转交 Livzon 失败: message_id=%s", message_id
            )
            return
    logger.info(
        "共享飞书应用消息已转交 Livzon: message_id=%s outcome=%s",
        message_id,
        result.get("status") if isinstance(result, dict) else "unknown",
    )


def _on_bitable_record_changed(data: P2DriveFileBitableRecordChangedV1) -> None:
    event = data.event
    if not event:
        return

    file_token = event.file_token or ""
    table_id = event.table_id or ""
    actions = [
        {
            "record_id": action.record_id,
            "action": action.action,
        }
        for action in (event.action_list or [])
    ]

    logger.info(
        "全局飞书收到多维表变更: file_token=%s table_id=%s revision=%s actions=%s",
        file_token,
        table_id,
        event.revision,
        len(actions),
    )

    if _main_loop is None:
        logger.error("主 event loop 未设置，无法处理多维表变更事件")
        return

    future = asyncio.run_coroutine_threadsafe(
        _handle_bitable_record_changed_async(
            file_token=file_token,
            table_id=table_id,
            revision=event.revision,
            update_time=event.update_time,
            actions=actions,
        ),
        _main_loop,
    )
    try:
        future.result(timeout=120)
    except Exception:
        logger.exception("异步处理多维表变更事件超时或异常")


async def _handle_bitable_record_changed_async(
    *,
    file_token: str,
    table_id: str,
    revision: int | None,
    update_time: int | None,
    actions: list[dict[str, str | None]],
) -> None:
    await event_bus.publish(
        FEISHU_BITABLE_RECORD_CHANGED_EVENT,
        {
            "file_token": file_token,
            "table_id": table_id,
            "revision": revision,
            "update_time": update_time,
            "actions": actions,
        },
    )
