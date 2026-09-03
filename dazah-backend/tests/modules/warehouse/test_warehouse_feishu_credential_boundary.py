from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.warehouse import service, ws_client


@pytest.mark.asyncio
async def test_warehouse_clients_use_own_configuration(monkeypatch):
    instance = service.WarehouseService(AsyncMock())
    instance.repo.get_active_feishu_config = AsyncMock(
        return_value=SimpleNamespace(
            app_id="warehouse-app", encrypted_app_secret="encrypted"
        )
    )
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "warehouse-secret")
    client = await instance._get_feishu_client()
    bitable = await instance._get_bitable_client("base")
    assert (client.app_id, client.app_secret) == ("warehouse-app", "warehouse-secret")
    assert (bitable.client.app_id, bitable.client.app_secret) == (
        client.app_id,
        client.app_secret,
    )


@pytest.mark.asyncio
async def test_warehouse_ws_without_own_config_does_not_start(monkeypatch):
    from app.modules.warehouse.repository import WarehouseRepository

    monkeypatch.setattr(ws_client, "async_session_factory", lambda: AsyncMock())
    monkeypatch.setattr(
        WarehouseRepository, "get_active_feishu_config", AsyncMock(return_value=None)
    )
    start = AsyncMock()
    monkeypatch.setattr(ws_client, "restart_ws_with_config", start)
    status = await ws_client.start_ws_from_db()
    assert not status.enabled
    assert "独立仓储" in status.last_error
    start.assert_not_awaited()
