"""液体入库两页（liquid-raw-inbound / liquid-sugar-inbound）配置与接口测试。

两页复用 warehouse 模块通用 material-pages CRUD，本文件验证新增 pageKey：
- 页面注册表保留 page_key/标题（绑定字段留空，属部署数据）
- 数据源解析只认 DB 配置；未绑定占位可被 _page_binding_missing 识别
- 日期倒序登记（增量同步与列表排序；液糖表业务日期是「日期」而非公式列「入库日期」）
- 列表接口对该 pageKey 路由正常（绑定来自设置页 DB 配置）
- 未注册的 pageKey 返回 404（可预期分支不得转 500）
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.modules.warehouse.feishu_material_pages import (
    FEISHU_WAREHOUSE_MATERIAL_PAGES,
    FeishuWarehouseMaterialPage,
)
from app.modules.warehouse.service import (
    _DATE_SORT_DESC_FIELDS,
    WarehouseService,
)

PAGES = {
    "liquid-raw-inbound": ("液体原辅料入库", "tbljj75DiA6BDt4D", "入库日期"),
    "liquid-sugar-inbound": ("液糖入库", "tblRX5IjxkjaFkqp", "日期"),
}


def test_page_mappings_registered() -> None:
    """两个 pageKey 已注册（标题保留；绑定字段一律留空，属部署数据）。"""
    for page_key, (title, _table_id, _date_field) in PAGES.items():
        page = FEISHU_WAREHOUSE_MATERIAL_PAGES[page_key]
        assert page.page_key == page_key
        assert page.title == title
        assert page.table_id == ""
        assert page.app_token == ""


def test_date_sort_desc_registered() -> None:
    """按业务日期倒序：液糖用「日期」，其「入库日期」为公式列。"""
    for page_key, (_, _, date_field) in PAGES.items():
        assert _DATE_SORT_DESC_FIELDS[page_key] == date_field


def test_liquid_pages_in_edit_scope_permission() -> None:
    """液体页面必须登记细分编辑权限（raw scope），否则编辑/删除必 403。"""
    from app.modules.warehouse.api import WAREHOUSE_EDIT_SCOPE_PERMISSION

    for page_key in PAGES:
        assert WAREHOUSE_EDIT_SCOPE_PERMISSION[page_key] == "warehouse:raw:write"


async def test_get_material_page_config_unbound_placeholder_and_db_binding() -> None:
    """DB 无配置时返回未绑定占位；有 DB 配置时按配置解析。"""
    for page_key in PAGES:
        service = WarehouseService.__new__(WarehouseService)
        service.repo = AsyncMock()
        service.repo.get_page_feishu_config = AsyncMock(return_value=None)

        config = await service._get_material_page_config(page_key)
        assert config.page_key == page_key
        assert service._page_binding_missing(config)

        service.repo.get_page_feishu_config = AsyncMock(
            return_value={
                "page_key": page_key,
                "app_token": "app-token-liquid",
                "table_id": "tblLiquid",
                "table_name": "液体原辅料入库",
                "view_id": None,
            }
        )
        bound = await service._get_material_page_config(page_key)
        assert bound.table_id == "tblLiquid"
        assert bound.app_token == "app-token-liquid"
        assert not service._page_binding_missing(bound)


async def test_get_material_page_returns_configured_title(client: AsyncClient) -> None:
    """列表接口按设置页 DB 绑定读取，返回液体原辅料入库页配置及动态列。"""
    page_key, (title, _, _) = next(iter(PAGES.items()))
    bound_config = FeishuWarehouseMaterialPage(
        page_key=page_key,
        title=title,
        table_id="tblLiquid",
        app_token="app-token-liquid",
    )
    with (
        patch.object(
            WarehouseService,
            "_get_material_page_config",
            new=AsyncMock(return_value=bound_config),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_fields",
            new=AsyncMock(
                return_value=[
                    {"field_name": "入库日期"},
                    {"field_name": "物料名称"},
                    {"field_name": "备注"},
                ]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_liquid_1",
                        "fields": {
                            "入库日期": "2026/09/01",
                            "物料名称": "液碱",
                            "备注": "槽车入库",
                        },
                    }
                ]
            ),
        ),
    ):
        response = await client.get(
            f"/api/v1/warehouse/material-pages/{page_key}",
            headers={"X-Dazah-Page-Key": f"warehouse:materials:{page_key}"},
            params={"page": 1, "page_size": 20, "source": "feishu"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == page_key
    assert body["data"]["page_title"] == title
    assert body["data"]["rows"] == [
        {
            "入库日期": "2026/09/01",
            "物料名称": "液碱",
            "备注": "槽车入库",
            "__record_id": "rec_liquid_1",
        }
    ]


async def test_unregistered_page_key_returns_404(client: AsyncClient) -> None:
    """未注册的 pageKey 属可预期输入错误，必须返回 404 而非 500。"""
    response = await client.get(
        "/api/v1/warehouse/material-pages/liquid-inbound-not-exist",
        headers={"X-Dazah-Page-Key": "warehouse:materials:liquid-raw-inbound"},
    )

    assert response.status_code == 404
