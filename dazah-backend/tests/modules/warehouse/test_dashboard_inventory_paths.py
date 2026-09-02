from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.warehouse import service as warehouse
from app.modules.warehouse.feishu_material_pages import FeishuWarehouseMaterialPage
from app.modules.warehouse.schemas import WarehouseFeishuColumn
from app.platform.identity.data_scope import DepartmentScope


def _service() -> warehouse.WarehouseService:
    instance = warehouse.WarehouseService.__new__(warehouse.WarehouseService)
    instance.repo = SimpleNamespace()
    instance._page_cache = {}
    instance._field_meta_cache = {}
    instance._table_fields_cache = {}
    instance._dashboard_cache = {}
    return instance


@pytest.mark.asyncio
async def test_inventory_sync_covers_raw_packaging_product_branches() -> None:
    instance = _service()
    page = FeishuWarehouseMaterialPage("raw-summary", "原辅料", "tbl", "app")
    columns = [
        WarehouseFeishuColumn(key=key, title=key, field_type=1)
        for key in (
            "使用产品/类别",
            "物料名称",
            "ERP编号",
            "规格",
            "单位",
            "可用库存",
            "安全库存（30天）",
            "本日结存",
            "前台库存",
            "预警",
            "产品名称",
            "包装规格",
            "订单量",
            "待检数量",
            "合格数量",
            "小计",
            "剩余量",
        )
    ]
    row = {
        "__record_id": "rec-1",
        "使用产品/类别": "原料",
        "物料名称": "物料",
        "ERP编号": "ERP-1",
        "规格": "1kg",
        "单位": "kg",
        "可用库存": "12",
        "安全库存（30天）": "5",
        "本日结存": "10",
        "前台库存": "1",
        "预警": "正常",
        "产品名称": "成品",
        "包装规格": "箱",
        "订单量": "2",
        "待检数量": "1",
        "合格数量": "3",
        "小计": "4",
        "剩余量": "5",
    }
    instance.fetch_material_page_from_feishu = AsyncMock(  # type: ignore[method-assign]
        return_value=(page, columns, [row, {"__record_id": "empty"}], {})
    )
    instance.upsert_raw_material_snapshot = AsyncMock()  # type: ignore[method-assign]
    instance.upsert_packaging_snapshot = AsyncMock()  # type: ignore[method-assign]
    instance.upsert_product_snapshot = AsyncMock()  # type: ignore[method-assign]

    assert await instance._sync_inventory_page("raw-summary") == 1
    assert await instance._sync_inventory_page("packaging-summary") == 1
    assert await instance._sync_inventory_page("product-summary") == 1
    assert instance.upsert_raw_material_snapshot.await_count == 1
    assert instance.upsert_packaging_snapshot.await_count == 1
    assert instance.upsert_product_snapshot.await_count == 1
    with pytest.raises(ValueError):
        await instance._sync_inventory_page("unknown")


@pytest.mark.asyncio
async def test_warehouse_dashboards_and_scope_filter_cover_real_aggregations() -> None:
    instance = _service()
    today = datetime.now(warehouse.CHINA_TIMEZONE).date().isoformat()

    pages = {
        "raw-summary": [
            {
                "物料名称": "预混剂",
                "使用产品/类别": "预混剂",
                "安全库存（30天）": 10,
                "本日结存": 12,
                "前台库存": 9,
                "预警": "正常",
            },
            {
                "物料名称": "缺货物料",
                "使用产品/类别": "原料",
                "安全库存（30天）": 20,
                "本日结存": 3,
                "前台库存": 1,
                "预警": "库存严重不足",
            },
        ],
        "raw-detail": [
            {"物料名称": "物料A", "质量状态": "合格", "本日结存": 2},
            {
                "物料名称": "物料B",
                "质量状态": "待验",
                "厂内批号": "B1",
                "库区": "一号库",
                "本日结存": 1,
            },
            {"物料名称": "物料C", "质量状态": "不合格"},
        ],
        "raw-ledger": [{"出库日期": today, "出库数量": 4}],
        "packaging-ledger": [{"出库日期": today, "领用数量（条/个）": 2}],
        "inbound-ledger": [
            {"入库日期": today, "物料类别": "原料", "物料名称": "物料A", "入库数量": 6}
        ],
        "hardware-summary": [{"金额（元）": 100}],
        "hardware-stock-amount": [
            {"车间名称": "合计", "一车间": 60, "二车间": 40, "总金额": 100}
        ],
        "hardware-inbound-ledger": [
            {"日期": today, "物料名称": "螺丝", "入库量": 2, "单价（元）": 3}
        ],
        "hardware-outbound-ledger": [
            {"日期": today, "物料名称": "螺丝", "金额": 8, "归属库区": "一车间"}
        ],
        "product-summary": [{"产品名称": "产品A", "合格数量": 8, "待检数量": 2}],
        "product-shipping": [{"产品名称": "产品A", "发货数量": 4, "日期": today}],
        "product-inbound-monthly": [{"月份": "2026-01", "产品A": 3, "产品B": 0}],
        "product-outbound-monthly": [{"月份": "2026-01", "产品A": 1, "产品B": 0}],
    }

    async def load(page_key: str, _force: bool) -> list[dict[str, object | None]]:
        return pages[page_key]

    instance._load_page_rows = load  # type: ignore[method-assign]
    raw = await instance._build_raw_dashboard(detail=True)
    hardware = await instance._build_hardware_dashboard(detail=True)
    product = await instance._build_product_dashboard(detail=True)
    assert raw["safety"]["total"] == 2
    assert raw["quality"]["待验"] == 1
    assert hardware["stock_amount"] == 100
    assert hardware["inbound_30d_total"] == 6
    assert product["qualified"] == 8
    assert product["product_monthly_inbound"]["产品A"][0]["quantity"] == 3

    instance._build_raw_dashboard = AsyncMock(return_value=raw)  # type: ignore[method-assign]
    cached = await instance.get_dashboard_data("raw", detail=True)
    assert cached["safety"]["total"] == 2
    with pytest.raises(Exception):
        await instance.get_dashboard_data("bad")

    filtered = warehouse.WarehouseService._apply_dashboard_scope(
        hardware,
        "hardware",
        DepartmentScope(is_all=False, department_names={"一车间"}),
    )
    assert filtered["stock_amount"] == 60
    assert filtered["outbound_30d_total"] == 8
