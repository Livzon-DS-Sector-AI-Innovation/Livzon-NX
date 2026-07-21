"""Warehouse Feishu event handlers."""

import logging
from typing import Any

from app.core.database import async_session_factory
from app.core.events import event_bus
from app.modules.warehouse.service import WarehouseService
from app.platform.integrations.feishu.utils import FEISHU_BITABLE_RECORD_CHANGED_EVENT

logger = logging.getLogger(__name__)
_registered = False


async def handle_bitable_record_changed(
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
                "仓储飞书多维表变更事件已处理: table=%s status=%s",
                result.get("table_kind"),
                result.get("status"),
            )


async def _handle_bitable_record_changed_event(data: Any) -> None:
    if not isinstance(data, dict):
        logger.warning("仓储飞书事件 payload 非法: %r", data)
        return

    await handle_bitable_record_changed(
        file_token=str(data.get("file_token") or ""),
        table_id=str(data.get("table_id") or ""),
        revision=data.get("revision"),
        update_time=data.get("update_time"),
        actions=data.get("actions") or [],
    )


def register_feishu_event_handlers() -> None:
    global _registered
    if _registered:
        return
    event_bus.subscribe(
        FEISHU_BITABLE_RECORD_CHANGED_EVENT,
        _handle_bitable_record_changed_event,
    )
    _registered = True
