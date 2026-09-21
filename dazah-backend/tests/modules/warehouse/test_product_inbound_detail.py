"""成品入库明细页（product-inbound-detail）配置与接口测试。

该子页面复用 warehouse 模块通用 material-pages CRUD（列表/详情/编辑/删除），
本文件验证新增的 pageKey 配置与路由：
- 页面注册表保留 page_key/标题（绑定字段留空，属部署数据）
- 数据源解析只认 DB 配置；未绑定占位可被 _page_binding_missing 识别
- 入库日期倒序登记（保证增量同步与列表排序）
- 列表 / 详情接口对该 pageKey 路由正常
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

PAGE_KEY = "product-inbound-detail"


def test_page_mapping_registered() -> None:
    """pageKey 已注册（标题保留；绑定字段一律留空，属部署数据）。"""
    page = FEISHU_WAREHOUSE_MATERIAL_PAGES[PAGE_KEY]
    assert page.page_key == PAGE_KEY
    assert page.title == "成品入库明细"
    assert page.table_id == ""
    assert page.app_token == ""


async def test_get_material_page_config_unbound_placeholder_and_db_binding() -> None:
    """DB 无配置时返回未绑定占位；有 DB 配置时按配置解析。"""
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    service.repo.get_page_feishu_config = AsyncMock(return_value=None)

    config = await service._get_material_page_config(PAGE_KEY)
    assert config.page_key == PAGE_KEY
    assert service._page_binding_missing(config)

    service.repo.get_page_feishu_config = AsyncMock(
        return_value={
            "page_key": PAGE_KEY,
            "app_token": "app-token-product",
            "table_id": "tblInboundDetail",
            "table_name": "成品入库明细",
            "view_id": None,
        }
    )
    bound = await service._get_material_page_config(PAGE_KEY)
    assert bound.table_id == "tblInboundDetail"
    assert bound.app_token == "app-token-product"
    assert not service._page_binding_missing(bound)


def test_date_sort_desc_registered() -> None:
    """按入库日期倒序，保证增量同步与列表排序正确。"""
    assert _DATE_SORT_DESC_FIELDS[PAGE_KEY] == "入库日期"


async def test_get_material_page_returns_configured_title(client: AsyncClient) -> None:
    """列表接口按设置页 DB 绑定读取，返回成品入库明细页配置及动态列。"""
    bound_config = FeishuWarehouseMaterialPage(
        page_key=PAGE_KEY,
        title="成品入库明细",
        table_id="tblInboundDetail",
        app_token="app-token-product",
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
                    {"field_name": "产品名称"},
                    {"field_name": "入库车间"},
                ]
            ),
        ),
        patch.object(
            WarehouseService,
            "fetch_feishu_table_records",
            new=AsyncMock(
                return_value=[
                    {
                        "record_id": "rec_inbound_1",
                        "fields": {
                            "入库日期": "2026/08/25",
                            "产品名称": "L-苯丙氨酸",
                            "入库车间": "201一车间",
                        },
                    }
                ]
            ),
        ),
    ):
        response = await client.get(
            f"/api/v1/warehouse/material-pages/{PAGE_KEY}",
            headers={
                "X-Dazah-Page-Key": (
                    "warehouse:product-inventory:product-inbound-detail"
                )
            },
            params={"page": 1, "page_size": 20, "source": "feishu"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["page_key"] == PAGE_KEY
    assert body["data"]["page_title"] == "成品入库明细"
    assert body["data"]["table_name"] == "成品入库明细"
    assert body["data"]["rows"] == [
        {
            "入库日期": "2026/08/25",
            "产品名称": "L-苯丙氨酸",
            "入库车间": "201一车间",
            "__record_id": "rec_inbound_1",
        }
    ]


async def test_get_record_detail_route_reachable(client: AsyncClient) -> None:
    """详情接口（含列表未展示字段）对该 pageKey 路由可达。"""
    detail_payload = {
        "record_id": "rec_inbound_1",
        "fields": [
            {
                "field_name": "入库日期",
                "field_type": 5,
                "readonly": False,
                "view_only": False,
                "editable": True,
                "options": None,
                "value": "2026/08/25",
            },
            {
                "field_name": "入库车间",
                "field_type": 3,
                "readonly": False,
                "view_only": False,
                "editable": True,
                "options": [{"id": "opt_1", "name": "201一车间"}],
                "value": "201一车间",
            },
            {
                "field_name": "QC确认人",
                "field_type": 11,
                "readonly": False,
                "view_only": False,
                "editable": False,
                "options": None,
                "value": "张三",
            },
        ],
    }
    with patch.object(
        WarehouseService,
        "get_material_page_record_detail",
        new=AsyncMock(return_value=detail_payload),
    ):
        response = await client.get(
            f"/api/v1/warehouse/material-pages/{PAGE_KEY}/records/rec_inbound_1",
            headers={
                "X-Dazah-Page-Key": (
                    "warehouse:product-inventory:product-inbound-detail"
                )
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["record_id"] == "rec_inbound_1"
    assert [field["field_name"] for field in body["data"]["fields"]] == [
        "入库日期",
        "入库车间",
        "QC确认人",
    ]


async def test_unregistered_page_key_returns_404(client: AsyncClient) -> None:
    """未注册的 pageKey 属可预期输入错误，必须返回 404 而非 500。"""
    response = await client.get(
        "/api/v1/warehouse/material-pages/product-inbound-not-exist",
        headers={
            "X-Dazah-Page-Key": "warehouse:product-inventory:product-inbound-detail"
        },
    )

    assert response.status_code == 404
