"""Warehouse page feishu config management tests.

测试页面飞书配置管理的 CRUD 操作和缓存清除逻辑。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import AppException
from app.modules.warehouse.service import WarehouseService


async def _make_service() -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = None  # type: ignore[assignment]
    service._page_cache = {}
    service._field_meta_cache = {}
    service._table_fields_cache = {}
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


@pytest.mark.asyncio
async def test_update_page_feishu_config_resolves_wiki_link() -> None:
    """知识库（/wiki/）链接在保存页面配置时自动解析为真正的 app_token"""
    service = await _make_service()

    saved: dict = {}

    class _Repo:
        async def get_active_feishu_config(self) -> object:
            return SimpleNamespace(app_id="cli_app", encrypted_app_secret="enc")

        async def upsert_page_feishu_config(self, config: dict) -> None:
            saved.update(config)

    service.repo = _Repo()  # type: ignore[assignment]
    client = SimpleNamespace(
        get_wiki_node=AsyncMock(
            return_value={
                "obj_type": "bitable",
                "obj_token": "NIEJbSxylaHBp4shlPjcpVSzXn2e",
            }
        )
    )
    with patch.object(
        WarehouseService,
        "_build_feishu_client",
        new=lambda self, config, token: client,
    ):
        await service.update_page_feishu_config(
            "product-inbound-monthly",
            {
                "page_key": "product-inbound-monthly",
                "app_token": (
                    "https://j0eukrlohu.feishu.cn/wiki/TeBUwZkJEiOPK2kKLxxcZ1SCnWg"
                    "?table=tblivbUvnYDjATiL"
                ),
                "table_id": "tblivbUvnYDjATiL",
                "table_name": "新表名",
                "view_id": None,
            },
        )

    assert saved["app_token"] == "NIEJbSxylaHBp4shlPjcpVSzXn2e"
    client.get_wiki_node.assert_awaited_once_with("TeBUwZkJEiOPK2kKLxxcZ1SCnWg")


@pytest.mark.asyncio
async def test_update_page_feishu_config_rejects_non_bitable_wiki_node() -> None:
    """知识库节点不是多维表格时返回明确业务错误，不落库"""
    service = await _make_service()

    class _Repo:
        async def get_active_feishu_config(self) -> object:
            return SimpleNamespace(app_id="cli_app", encrypted_app_secret="enc")

        async def upsert_page_feishu_config(self, config: dict) -> None:
            raise AssertionError("不应在节点类型不匹配时落库")

    service.repo = _Repo()  # type: ignore[assignment]
    client = SimpleNamespace(
        get_wiki_node=AsyncMock(
            return_value={"obj_type": "doc", "obj_token": "doxcn123"}
        )
    )
    with patch.object(
        WarehouseService,
        "_build_feishu_client",
        new=lambda self, config, token: client,
    ):
        with pytest.raises(AppException, match="不是多维表格"):
            await service.update_page_feishu_config(
                "product-inbound-monthly",
                {
                    "page_key": "product-inbound-monthly",
                    "app_token": "https://example.feishu.cn/wiki/DocNode123",
                    "table_id": "tbl1",
                    "table_name": "文档节点",
                    "view_id": None,
                },
            )


@pytest.mark.asyncio
async def test_list_page_feishu_config_tables_resolves_wiki_and_lists() -> None:
    """读子表接口：wiki 链接解析为真正 app_token，并返回规范化子表列表"""
    service = await _make_service()

    class _Repo:
        async def get_active_feishu_config(self) -> object:
            return SimpleNamespace(app_id="cli_app", encrypted_app_secret="enc")

    service.repo = _Repo()  # type: ignore[assignment]
    client = SimpleNamespace(
        get_wiki_node=AsyncMock(
            return_value={
                "obj_type": "bitable",
                "obj_token": "NIEJbSxylaHBp4shlPjcpVSzXn2e",
            }
        ),
        list_tables=AsyncMock(
            return_value=[
                {"table_id": "blkSTe791W95CdeO", "name": "原辅料进出台账"},
                {"table_id": "", "name": "invalid"},
                {"table_id": "blk2", "name": ""},
            ]
        ),
    )
    with patch.object(
        WarehouseService,
        "_build_feishu_client",
        new=lambda self, config, token: client,
    ):
        resolved, tables = await service.list_page_feishu_config_tables(
            "https://j0eukrlohu.feishu.cn/wiki/TeBUwZkJEiOPK2kKLxxcZ1SCnWg"
        )

    assert resolved == "NIEJbSxylaHBp4shlPjcpVSzXn2e"
    assert tables == [
        {"table_id": "blkSTe791W95CdeO", "table_name": "原辅料进出台账"}
    ]


@pytest.mark.asyncio
async def test_list_page_feishu_config_tables_requires_config() -> None:
    """未保存仓储飞书应用配置时返回明确业务错误"""
    service = await _make_service()

    class _Repo:
        async def get_active_feishu_config(self) -> None:
            return None

    service.repo = _Repo()  # type: ignore[assignment]
    with pytest.raises(AppException, match="请先保存仓储飞书应用配置"):
        await service.list_page_feishu_config_tables("bascn123")
