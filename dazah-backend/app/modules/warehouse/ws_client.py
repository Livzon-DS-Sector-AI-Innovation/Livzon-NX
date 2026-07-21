"""Warehouse Feishu WebSocket lifecycle."""

import asyncio
import logging
from datetime import UTC, datetime

import lark_oapi as lark
from lark_oapi.api.drive.v1 import P2DriveFileBitableRecordChangedV1

from app.core.database import async_session_factory
from app.core.secrets import decrypt_secret
from app.modules.warehouse.feishu_client import WarehouseFeishuClient
from app.modules.warehouse.repository import WarehouseRepository
from app.modules.warehouse.schemas import WarehouseFeishuWsStatus
from app.modules.warehouse.service import WarehouseService
from app.platform.integrations.feishu.ws_client import start_ws_client, stop_ws_client

logger = logging.getLogger(__name__)

_WS_NAME = "warehouse-feishu-ws"
_main_loop: asyncio.AbstractEventLoop | None = None
_enabled = False
_connected = False
_app_id: str | None = None
_app_tokens: dict[str, str] = {}
_last_started_at: datetime | None = None
_last_error: str | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _build_event_handler() -> lark.EventDispatcherHandler:
    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_drive_file_bitable_record_changed_v1(_on_bitable_record_changed)
        .build()
    )


def _on_bitable_record_changed(data: P2DriveFileBitableRecordChangedV1) -> None:
    event = data.event
    if not event:
        return
    actions = [
        {
            "record_id": action.record_id,
            "action": action.action,
        }
        for action in (event.action_list or [])
    ]
    if _main_loop is None:
        logger.error("仓储飞书 WS 主 event loop 未设置")
        return
    future = asyncio.run_coroutine_threadsafe(
        _handle_bitable_record_changed(
            file_token=event.file_token or "",
            table_id=event.table_id or "",
            revision=event.revision,
            update_time=event.update_time,
            actions=actions,
        ),
        _main_loop,
    )
    try:
        future.result(timeout=120)
    except Exception:
        logger.exception("仓储飞书多维表事件异步处理失败")


async def _handle_bitable_record_changed(
    *,
    file_token: str,
    table_id: str,
    revision: int | None,
    update_time: int | None,
    actions: list[dict[str, str | None]],
) -> None:
    async with async_session_factory() as session:
        service = WarehouseService(session)
        result = await service.handle_feishu_bitable_record_changed(
            file_token=file_token,
            table_id=table_id,
            revision=revision,
            update_time=update_time,
            actions=actions,
        )
        if result.get("matched"):
            logger.info(
                "仓储飞书 WS 事件已处理: table=%s status=%s",
                result.get("table_kind"),
                result.get("status"),
            )


async def start_ws_from_db() -> WarehouseFeishuWsStatus:
    global _last_error
    if _main_loop is None:
        set_main_loop(asyncio.get_running_loop())

    try:
        async with async_session_factory() as session:
            repo = WarehouseRepository(session)
            config = await repo.get_active_feishu_config()
            if not config:
                await stop_ws()
                _last_error = "未启用仓储飞书配置"
                return await get_ws_status()

            return await restart_ws_with_config(
                app_id=config.app_id,
                app_secret=decrypt_secret(config.encrypted_app_secret),
                app_tokens=WarehouseService._config_app_tokens(config),
            )
    except Exception as exc:
        await stop_ws()
        _last_error = f"读取仓储飞书配置失败：{exc}"
        logger.warning(_last_error)
        return await get_ws_status()


async def restart_ws_from_db() -> WarehouseFeishuWsStatus:
    return await start_ws_from_db()


async def restart_ws_with_config(
    *,
    app_id: str,
    app_secret: str,
    app_tokens: dict[str, str],
) -> WarehouseFeishuWsStatus:
    global _app_id, _app_tokens, _connected, _enabled, _last_error, _last_started_at
    if _main_loop is None:
        set_main_loop(asyncio.get_running_loop())

    stop_ws_client(_WS_NAME)
    _enabled = bool(app_id and app_secret and app_tokens)
    _connected = False
    _app_id = app_id or None
    _app_tokens = dict(app_tokens)
    _last_error = None

    if not _enabled:
        _last_error = "App ID、App Secret 或业务域 app_token 未配置"
        return await get_ws_status()

    try:
        for app_token in app_tokens.values():
            client = WarehouseFeishuClient(
                app_id=app_id,
                app_secret=app_secret,
                app_token=app_token,
            )
            await client.subscribe_bitable()
        start_ws_client(
            app_id=app_id,
            app_secret=app_secret,
            event_handler=_build_event_handler(),
            name=_WS_NAME,
        )
        _connected = True
        _last_started_at = datetime.now(UTC)
    except Exception as exc:
        _connected = False
        _last_error = str(exc)
        logger.exception("仓储飞书 WS 启动失败")
    return await get_ws_status()


async def stop_ws() -> None:
    global _app_tokens, _connected, _enabled
    stop_ws_client(_WS_NAME)
    _connected = False
    _enabled = False
    _app_tokens = {}


async def get_ws_status() -> WarehouseFeishuWsStatus:
    return WarehouseFeishuWsStatus(
        enabled=_enabled,
        connected=_connected,
        app_id=_app_id,
        app_tokens=_app_tokens,
        last_started_at=_last_started_at,
        last_error=_last_error,
    )
