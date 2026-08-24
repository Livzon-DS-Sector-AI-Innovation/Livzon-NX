"""Global Feishu business-data event handler.

Livzon Agent conversations and cards are consumed exclusively by Hermes
Gateway. This dispatcher intentionally registers only Bitable change events.
"""

import asyncio
import logging

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.api.drive.v1 import (  # type: ignore[import-untyped]
    P2DriveFileBitableRecordChangedV1,
)

from app.core.events import event_bus
from app.platform.integrations.feishu.utils import FEISHU_BITABLE_RECORD_CHANGED_EVENT

logger = logging.getLogger(__name__)
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def build_event_handler() -> lark.EventDispatcherHandler:
    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_drive_file_bitable_record_changed_v1(_on_bitable_record_changed)
        .build()
    )


def _on_bitable_record_changed(
    data: P2DriveFileBitableRecordChangedV1,
) -> None:
    event = data.event
    if not event:
        return
    file_token = event.file_token or ""
    table_id = event.table_id or ""
    actions = [
        {"record_id": action.record_id, "action": action.action}
        for action in (event.action_list or [])
    ]
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
