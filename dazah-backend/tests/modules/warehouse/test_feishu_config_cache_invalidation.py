"""仓储飞书配置保存后必须清空模块同步客户端缓存（换凭证即换即用）。

_after_feishu_config_saved 在 create / update 两条保存路径都会执行；
一旦清理逻辑被挪走或丢失，旧凭证会一直服务同步且无测试报错。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.warehouse import service as service_module
from app.modules.warehouse.schemas import WarehouseFeishuConfigUpsert
from app.modules.warehouse.service import WarehouseService


@pytest.fixture(autouse=True)
def clean_material_sync_clients() -> object:
    service_module._MATERIAL_SYNC_CLIENTS.clear()
    yield
    service_module._MATERIAL_SYNC_CLIENTS.clear()


@pytest.fixture(autouse=True)
def patch_ws_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.warehouse.ws_client.restart_ws_from_db", AsyncMock()
    )
    monkeypatch.setattr("app.modules.warehouse.ws_client.stop_ws", AsyncMock())
    monkeypatch.setattr(service_module, "encrypt_secret", lambda value: f"enc:{value}")


def _service(existing: SimpleNamespace | None) -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = SimpleNamespace(
        session=SimpleNamespace(
            commit=AsyncMock(),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        ),
        get_any_feishu_config=AsyncMock(return_value=existing),
        save_feishu_config=AsyncMock(
            side_effect=lambda config: setattr(config, "id", uuid4())
        ),
    )
    return service


def _existing_config(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "config_name": "仓储配置",
        "app_id": "old-app",
        "encrypted_app_secret": "old-encrypted",
        "timezone": "Asia/Shanghai",
        "daily_sync_time": "02:00",
        "is_active": True,
        "remark": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_save_config_clears_cache_on_update() -> None:
    """更新已有配置（update 路径）后缓存被清空。"""
    service = _service(_existing_config())
    service_module._MATERIAL_SYNC_CLIENTS["app-token-x"] = object()

    await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(app_id="new-app", app_secret="new-secret")
    )

    assert service_module._MATERIAL_SYNC_CLIENTS == {}


@pytest.mark.asyncio
async def test_save_config_clears_cache_on_create() -> None:
    """首次保存配置（create 路径）后缓存被清空。"""
    service = _service(None)
    service_module._MATERIAL_SYNC_CLIENTS["app-token-x"] = object()

    await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(app_id="new-app", app_secret="new-secret")
    )

    assert service_module._MATERIAL_SYNC_CLIENTS == {}


@pytest.mark.asyncio
async def test_save_config_deactivated_stops_ws_and_clears_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """停用配置：走 stop_ws 分支，缓存同样被清空。"""
    stop_mock = AsyncMock()
    monkeypatch.setattr("app.modules.warehouse.ws_client.stop_ws", stop_mock)
    service = _service(_existing_config(is_active=False))
    service_module._MATERIAL_SYNC_CLIENTS["app-token-x"] = object()

    await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(
            app_id="new-app", app_secret="new-secret", is_active=False
        )
    )

    assert service_module._MATERIAL_SYNC_CLIENTS == {}
    stop_mock.assert_awaited_once()
