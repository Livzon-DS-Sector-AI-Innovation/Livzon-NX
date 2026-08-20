"""Production Feishu WebSocket lifecycle."""

import asyncio
import logging
from datetime import UTC, datetime

import lark_oapi as lark
from lark_oapi.api.drive.v1 import P2DriveFileBitableRecordChangedV1
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig
from app.modules.production.production_plan_service import sync_config_by_target
from app.platform.integrations.feishu.ws_client import start_ws_client, stop_ws_client

logger = logging.getLogger(__name__)

_WS_NAME = "production-feishu-ws"
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
    file_token = event.file_token or ""
    table_id = event.table_id or ""
    if _main_loop is None:
        return
    future = asyncio.run_coroutine_threadsafe(
        _handle_bitable_record_changed(file_token, table_id), _main_loop
    )
    try:
        future.result(timeout=120)
    except Exception:
        logger.exception("生产飞书 WS 事件处理失败")


async def _handle_bitable_record_changed(file_token: str, table_id: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProductionFeishuConfig).where(
                ProductionFeishuConfig.bitable_app_token == file_token,
                ProductionFeishuConfig.table_id == table_id,
                ProductionFeishuConfig.is_active,
                ProductionFeishuConfig.is_deleted.is_(False),
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return
        try:
            summary = await sync_config_by_target(config, session)
            await session.commit()
            logger.info(
                "生产飞书 WS 自动同步完成: %s 条",
                summary.get("created", 0) + summary.get("updated", 0),
            )
        except Exception:
            await session.rollback()
            logger.exception("生产飞书 WS 自动同步失败")


async def start_ws_from_db() -> dict:
    global _last_error
    if _main_loop is None:
        set_main_loop(asyncio.get_running_loop())

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ProductionFeishuConfig).where(
                    ProductionFeishuConfig.is_active,
                    ProductionFeishuConfig.is_deleted.is_(False),
                )
            )
            configs = list(result.scalars().all())
            if not configs:
                await stop_ws()
                _last_error = "未启用生产飞书配置"
                return await get_ws_status()

            # Start WS for the first config
            config = configs[0]
            return await restart_ws_with_config(
                app_id=config.app_id,
                app_secret=decrypt_secret(config.encrypted_app_secret),
                app_tokens={
                    config.product_name or config.name: config.bitable_app_token
                },
            )
    except Exception as exc:
        await stop_ws()
        _last_error = str(exc)
        return await get_ws_status()


async def restart_ws_from_db() -> dict:
    return await start_ws_from_db()


async def restart_ws_with_config(
    app_id: str, app_secret: str, app_tokens: dict[str, str]
) -> dict:
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
        _last_error = "App ID、App Secret 或 app_token 未配置"
        return await get_ws_status()

    try:
        for app_token in app_tokens.values():
            client = ProductionFeishuClient(
                app_id=app_id, app_secret=app_secret, app_token=app_token
            )
            await client.subscribe()
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
        logger.exception("生产飞书 WS 启动失败")
    return await get_ws_status()


async def stop_ws() -> None:
    global _connected, _enabled
    stop_ws_client(_WS_NAME)
    _connected = False
    _enabled = False


async def get_ws_status() -> dict:
    return {
        "connected": _connected,
        "enabled": _enabled,
        "last_error": _last_error,
    }
