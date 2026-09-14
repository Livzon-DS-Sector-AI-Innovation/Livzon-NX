"""液体入库两页（liquid-raw-inbound / liquid-sugar-inbound）配置与接口测试。

两页复用 warehouse 模块通用 material-pages CRUD，本文件验证新增 pageKey：
- 页面映射指向液体入库 Base（NX5Gbf…）的两张子表
- 数据源解析（DB 无配置时回退硬编码映射）
- 日期倒序登记（增量同步与列表排序；液糖表业务日期是「日期」而非公式列「入库日期」）
- 列表接口对该 pageKey 路由正常
- 未注册的 pageKey 返回 404（可预期分支不得转 500）
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.modules.warehouse.feishu_material_pages import (
    FEISHU_LIQUID_WAREHOUSE_APP_TOKEN,
    FEISHU_WAREHOUSE_MATERIAL_PAGES,
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
    """两个 pageKey 已注册到液体入库 Base，指向对应子表。"""
    for page_key, (title, table_id, _) in PAGES.items():
        page = FEISHU_WAREHOUSE_MATERIAL_PAGES[page_key]
        assert page.page_key == page_key
        assert page.title == title
        assert page.table_id == table_id
        assert page.app_token == FEISHU_LIQUID_WAREHOUSE_APP_TOKEN


def test_date_sort_desc_registered() -> None:
    """按业务日期倒序：液糖用「日期」，其「入库日期」为公式列。"""
    for page_key, (_, _, date_field) in PAGES.items():
        assert _DATE_SORT_DESC_FIELDS[page_key] == date_field


def test_liquid_base_in_edit_scope_permission() -> None:
    """液体 Base 必须登记细分编辑权限（raw scope），否则编辑/删除必 403。"""
    from app.modules.warehouse.api import WAREHOUSE_EDIT_SCOPE_PERMISSION

    assert (
        WAREHOUSE_EDIT_SCOPE_PERMISSION[FEISHU_LIQUID_WAREHOUSE_APP_TOKEN]
        == "warehouse:raw:write"
    )


async def test_get_material_page_config_falls_back_to_hardcoded() -> None:
    """数据库无配置时回退硬编码映射，仍返回液体入库子表。"""
    for page_key, (_, table_id, _) in PAGES.items():
        service = WarehouseService.__new__(WarehouseService)
        service.repo = AsyncMock()
        service.repo.get_page_feishu_config = AsyncMock(return_value=None)

        config = await service._get_material_page_config(page_key)

        assert config.page_key == page_key
        assert config.table_id == table_id
        assert config.app_token == FEISHU_LIQUID_WAREHOUSE_APP_TOKEN


async def test_get_material_page_returns_configured_title(client: AsyncClient) -> None:
    """列表接口返回液体原辅料入库页配置及动态列。"""
    page_key, (title, _, _) = next(iter(PAGES.items()))
    with (
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
