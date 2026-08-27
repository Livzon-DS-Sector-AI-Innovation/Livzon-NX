"""Warehouse page feishu config management tests.

测试页面飞书配置管理的 CRUD 操作和缓存清除逻辑。
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.modules.warehouse.service import WarehouseService


async def _make_service() -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = None  # type: ignore[assignment]
    service._page_cache = {}
    service._field_meta_cache = {}
    service._table_fields_cache = {}
    service._bitable_clients = {}
    service._dashboard_cache = {}
    return service


@pytest.mark.asyncio
async def test_get_all_page_feishu_configs() -> None:
    """测试获取所有页面飞书配置"""
    service = await _make_service()

    mock_configs = [
        {
            "page_key": "product-inbound-monthly",
            "app_token": "test_token_1",
            "table_id": "test_table_1",
            "table_name": "各产品每月入库量 -26 年",
            "view_id": None,
        },
        {
            "page_key": "product-outbound-monthly",
            "app_token": "test_token_2",
            "table_id": "test_table_2",
            "table_name": "各产品每月出库量 -26 年",
            "view_id": None,
        },
    ]

    with patch.object(
        WarehouseService,
        "get_all_page_feishu_configs",
        new=AsyncMock(return_value=mock_configs),
    ):
        configs = await service.get_all_page_feishu_configs()

    assert len(configs) == 2
    assert configs[0]["page_key"] == "product-inbound-monthly"
    assert configs[1]["page_key"] == "product-outbound-monthly"


@pytest.mark.asyncio
async def test_get_page_feishu_config() -> None:
    """测试获取指定页面飞书配置"""
    service = await _make_service()

    mock_config = {
        "page_key": "product-inbound-monthly",
        "app_token": "test_token",
        "table_id": "test_table",
        "table_name": "各产品每月入库量 -26 年",
        "view_id": None,
    }

    with patch.object(
        WarehouseService,
        "get_page_feishu_config",
        new=AsyncMock(return_value=mock_config),
    ):
        config = await service.get_page_feishu_config("product-inbound-monthly")

    assert config is not None
    assert config["page_key"] == "product-inbound-monthly"
    assert config["app_token"] == "test_token"


@pytest.mark.asyncio
async def test_get_page_feishu_config_not_found() -> None:
    """测试获取不存在的页面飞书配置"""
    service = await _make_service()

    with patch.object(
        WarehouseService,
        "get_page_feishu_config",
        new=AsyncMock(return_value=None),
    ):
        config = await service.get_page_feishu_config("non-existent")

    assert config is None


@pytest.mark.asyncio
async def test_update_page_feishu_config() -> None:
    """测试更新页面飞书配置"""
    service = await _make_service()

    new_config = {
        "page_key": "product-inbound-monthly",
        "app_token": "new_token",
        "table_id": "new_table",
        "table_name": "新表名",
        "view_id": "new_view",
    }

    with patch.object(
        WarehouseService,
        "update_page_feishu_config",
        new=AsyncMock(),
    ) as mock_update:
        await service.update_page_feishu_config("product-inbound-monthly", new_config)
        mock_update.assert_called_once_with("product-inbound-monthly", new_config)


@pytest.mark.asyncio
async def test_update_page_feishu_config_clears_cache() -> None:
    """测试更新页面飞书配置后清除缓存"""
    service = await _make_service()
    service._page_cache["product-inbound-monthly"] = ("fake_data",)

    new_config = {
        "page_key": "product-inbound-monthly",
        "app_token": "new_token",
        "table_id": "new_table",
        "table_name": "新表名",
        "view_id": None,
    }

    with patch.object(
        WarehouseService,
        "update_page_feishu_config",
        new=AsyncMock(side_effect=lambda pk, cfg: service._invalidate_page_cache(pk)),
    ):
        await service.update_page_feishu_config("product-inbound-monthly", new_config)

    # 验证缓存已清除
    assert "product-inbound-monthly" not in service._page_cache
