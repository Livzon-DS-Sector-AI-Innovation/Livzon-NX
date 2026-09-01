"""Warehouse dashboard aggregation unit tests.

仪表盘聚合逻辑纯函数化于 WarehouseService._build_*_dashboard，
测试通过 mock _load_page_rows 返回构造行数据验证统计口径。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.modules.warehouse.service import WarehouseService

# 参考“今天”必须跟随真实当前日期（东八区）：仪表盘按 datetime.now 的
# 当月/近 30 天窗口过滤，硬编码日期在跨月后会让断言必然失败。
CHINA = datetime.now(timezone(timedelta(hours=8)))


def _ms(dt) -> int:
    if isinstance(dt, datetime):
        return int(dt.timestamp() * 1000)
    return int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)


def _row(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items()}


async def _make_service() -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = None  # type: ignore[assignment]
    service._page_cache = {}
    service._field_meta_cache = {}
    service._table_fields_cache = {}
    service._dashboard_cache = {}
    return service


@pytest.mark.asyncio
async def test_raw_dashboard_aggregation() -> None:
    service = await _make_service()
    today = CHINA.date()
    day1 = today - timedelta(days=2)
    day2 = today - timedelta(days=1)

    rows_by_page = {
        "raw-summary": [
            {"物料名称": "葡萄糖", "本日结存": 100, "安全库存（30天）": 80, "预警": ""},
            {
                "物料名称": "酵母粉",
                "本日结存": 50,
                "安全库存（30天）": 100,
                "预警": "库存不足",
            },
            {
                "物料名称": "活性炭",
                "本日结存": 10,
                "安全库存（30天）": 50,
                "预警": "库存严重不足",
            },
            {"物料名称": "无安全库存物料", "本日结存": 999, "安全库存（30天）": ""},
        ],
        "raw-detail": [
            {"质量状态": "合格"},
            {"质量状态": "合格"},
            {"质量状态": "待验"},
            {"质量状态": "不合格"},
        ],
        "raw-ledger": [
            {"出库日期": _ms(day1), "出库数量": 100},
            {"出库日期": _ms(day2), "出库数量": 50},
            {"出库日期": _ms(today - timedelta(days=40)), "出库数量": 9999},
        ],
        "packaging-ledger": [
            {"出库日期": _ms(day1), "出库数量": 10},
            {"出库日期": _ms(day2), "出库数量": 20},
        ],
        "inbound-ledger": [
            {"入库日期": _ms(today.replace(day=1)), "入库数量": 500},
            {"入库日期": _ms(today - timedelta(days=60)), "入库数量": 999},
        ],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("raw")

    assert data["safety"] == {"total": 3, "ok": 1, "low": 2}
    assert data["quality"] == {"合格": 2, "待验": 1, "不合格": 1}
    assert data["packaging_outbound_30d_total"] == 30
    assert data["month_inbound_total"] == 500
    # 低库存 Top：严重不足优先
    assert data["low_stock_top"][0]["name"] == "活性炭"
    assert data["low_stock_top"][0]["warning"] == "库存严重不足"
    assert len(data["low_stock_top"]) == 2
    # 30 天趋势：出库日期窗口内合计 150
    assert sum(item["value"] for item in data["material_outbound_30d"]) == 150


@pytest.mark.asyncio
async def test_hardware_dashboard_aggregation() -> None:
    service = await _make_service()
    today = CHINA.date()
    day1 = today - timedelta(days=1)

    rows_by_page = {
        "hardware-summary": [
            {"金额（元）": 1000},
            {"金额（元）": 500},
        ],
        "hardware-stock-amount": [
            {
                "车间名称": "金额（元）",
                "101-1车间": 300,
                "202车间": 700,
                "总金额": 1000,
            },
        ],
        "hardware-inbound-ledger": [
            {"日期": _ms(day1), "入库量": 10, "单价（元）": 50},
            {"日期": _ms(today - timedelta(days=40)), "入库量": 100, "单价（元）": 50},
        ],
        "hardware-outbound-ledger": [
            {"日期": _ms(day1), "金额": 300, "归属库区": "101-1车间"},
            {"日期": _ms(day1), "金额": 200, "归属库区": "101-1车间"},
            {"日期": _ms(day1), "金额": 100, "归属库区": "202车间"},
            {
                "日期": _ms(today - timedelta(days=40)),
                "金额": 9999,
                "归属库区": "202车间",
            },
        ],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("hardware")

    assert data["stock_amount"] == 1500
    dept_stock = {item["dept"]: item["value"] for item in data["dept_stock"]}
    assert dept_stock == {"202车间": 700, "101-1车间": 300}
    assert data["inbound_30d_total"] == 500
    assert data["outbound_30d_total"] == 600
    dept_outbound = {item["dept"]: item["value"] for item in data["dept_outbound_30d"]}
    assert dept_outbound == {"101-1车间": 500, "202车间": 100}


@pytest.mark.asyncio
async def test_product_dashboard_aggregation() -> None:
    service = await _make_service()
    today = CHINA.date()
    day1 = today - timedelta(days=1)

    rows_by_page = {
        "product-summary": [
            {"产品名称": "L-苯丙氨酸", "合格数量": 1000, "待检数量": 200},
            {"产品名称": "L-色氨酸", "合格数量": 500, "待检数量": 0},
        ],
        "product-shipping": [
            {"产品名称": "L-苯丙氨酸", "发货数量": 300, "日期": _ms(day1)},
            {"产品名称": "L-色氨酸", "发货数量": 100, "日期": _ms(day1)},
        ],
        "product-inbound-monthly": [
            {"月份": "2026-01", "L-苯丙氨酸": 1000, "霉酚酸": 500},
            {"月份": "2026-02", "L-苯丙氨酸": 1200, "霉酚酸": 600},
        ],
        "product-outbound-monthly": [
            {"月份": "2026-01", "L-苯丙氨酸": 800, "霉酚酸": 400},
            {"月份": "2026-02", "L-苯丙氨酸": 900, "霉酚酸": 450},
        ],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("product")

    assert data["qualified"] == 1500
    assert data["pending"] == 200
    stock = {item["name"]: item["value"] for item in data["product_stock"]}
    assert stock == {"L-苯丙氨酸": 1200, "L-色氨酸": 500}
    outbound = {item["name"]: item["value"] for item in data["product_outbound"]}
    assert outbound == {"L-苯丙氨酸": 300, "L-色氨酸": 100}
    assert sum(item["value"] for item in data["shipping_30d_trend"]) == 400
    # 验证宽表解析
    assert "L-苯丙氨酸" in data["product_monthly_inbound"]
    assert "霉酚酸" in data["product_monthly_inbound"]
    assert len(data["product_monthly_inbound"]["L-苯丙氨酸"]) == 2
    # 验证零活动产品排查（当前测试数据中所有产品都有活动）
    assert len(data["zero_activity_products"]) == 0


@pytest.mark.asyncio
async def test_dashboard_invalid_group() -> None:
    service = await _make_service()
    with pytest.raises(HTTPException) as exc_info:
        await service.get_dashboard_data("unknown")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_product_dashboard_monthly_trend() -> None:
    """测试成品仪表盘每月趋势聚合"""
    service = await _make_service()

    rows_by_page = {
        "product-summary": [],
        "product-shipping": [],
        "product-inbound-monthly": [
            {"月份": "2026-01", "L-苯丙氨酸": 1000, "霉酚酸": 500},
            {"月份": "2026-02", "L-苯丙氨酸": 1200, "霉酚酸": 600},
            {"月份": "2026-03", "L-苯丙氨酸": 0, "霉酚酸": 700},
        ],
        "product-outbound-monthly": [
            {"月份": "2026-01", "L-苯丙氨酸": 800, "霉酚酸": 400},
            {"月份": "2026-02", "L-苯丙氨酸": 900, "霉酚酸": 450},
            {"月份": "2026-03", "L-苯丙氨酸": 1000, "霉酚酸": 0},
        ],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("product")

    # 验证入库宽表解析
    assert "L-苯丙氨酸" in data["product_monthly_inbound"]
    assert "霉酚酸" in data["product_monthly_inbound"]
    assert (
        len(data["product_monthly_inbound"]["L-苯丙氨酸"]) == 2
    )  # 2026-03 为 0 被过滤
    assert data["product_monthly_inbound"]["L-苯丙氨酸"][0]["month"] == "2026-01"
    assert data["product_monthly_inbound"]["L-苯丙氨酸"][0]["quantity"] == 1000

    # 验证出库宽表解析
    assert "L-苯丙氨酸" in data["product_monthly_outbound"]
    assert len(data["product_monthly_outbound"]["霉酚酸"]) == 2  # 2026-03 为 0 被过滤


@pytest.mark.asyncio
async def test_zero_activity_products() -> None:
    """测试 2026 年零活动产品排查"""
    service = await _make_service()

    inbound = {
        "L-苯丙氨酸": [{"month": "2026-01", "quantity": 1000}],
        "零活动产品 A": [],  # 整年无入库
    }
    outbound = {
        "L-苯丙氨酸": [{"month": "2026-01", "quantity": 800}],
        "零活动产品 A": [],  # 整年无出库
        "零活动产品 B": [],  # 整年无出库
    }

    result = service._find_zero_activity_products(inbound, outbound, year=2026)
    assert sorted(result) == ["零活动产品 A", "零活动产品 B"]


@pytest.mark.asyncio
async def test_raw_dashboard_safety_metric_alignment() -> None:
    """安全库存判定口径与飞书"预警"公式一致：预混剂按本日结存，其余按可用库存。"""
    service = await _make_service()

    rows_by_page = {
        "raw-summary": [
            # 非预混剂：结存达标但可用库存（结存-前台）不足 → 判定为不足
            {
                "物料名称": "L-酪氨酸",
                "使用产品/类别": "FA",
                "本日结存": 23875,
                "前台库存": 9000,
                "安全库存（30天）": 15000,
                "预警": "库存不足",
            },
            # 预混剂：按本日结存判定，达标
            {
                "物料名称": "氟苯尼考",
                "使用产品/类别": "预混剂",
                "本日结存": 2500,
                "前台库存": 99999,
                "安全库存（30天）": 2000,
                "预警": "",
            },
            # 可用库存低于安全库存一半 → 严重不足
            {
                "物料名称": "蔗糖",
                "使用产品/类别": "LV",
                "本日结存": 5450,
                "前台库存": 2500,
                "安全库存（30天）": 6000,
                "预警": "库存严重不足",
            },
            {"物料名称": "无安全库存", "本日结存": 999, "安全库存（30天）": ""},
        ],
        "raw-detail": [],
        "raw-ledger": [],
        "packaging-ledger": [],
        "inbound-ledger": [],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("raw")

    # 3 项有安全库存：L-酪氨酸不足、氟苯尼考达标、蔗糖不足 → ok=1, low=2
    assert data["safety"] == {"total": 3, "ok": 1, "low": 2}
    # 低库存 Top 严重不足优先
    assert data["low_stock_top"][0]["name"] == "蔗糖"
    assert data["low_stock_top"][0]["warning"] == "库存严重不足"
    # L-酪氨酸在旧口径下会被判达标，新口径判不足，且进入低库存列表
    assert {item["name"] for item in data["low_stock_top"]} == {"L-酪氨酸", "蔗糖"}


@pytest.mark.asyncio
async def test_raw_dashboard_detail_rows() -> None:
    """dashboard detail=1 时附加 KPI 明细行（卡片点击查看）。"""
    service = await _make_service()
    today = CHINA.date()

    rows_by_page = {
        "raw-summary": [
            {
                "物料名称": "葡萄糖",
                "使用产品/类别": "FA",
                "本日结存": 100,
                "前台库存": 0,
                "安全库存（30天）": 80,
                "预警": "",
            },
            {
                "物料名称": "酵母粉",
                "使用产品/类别": "FA",
                "本日结存": 50,
                "前台库存": 0,
                "安全库存（30天）": 100,
                "预警": "库存不足",
            },
        ],
        "raw-detail": [
            {
                "物料名称": "葡萄糖",
                "厂内批号": "2608001",
                "本日结存": 100,
                "质量状态": "待验",
                "库区": "原料库",
            },
            {"质量状态": "合格"},
        ],
        "raw-ledger": [],
        "packaging-ledger": [],
        "inbound-ledger": [
            {
                "入库日期": _ms(today.replace(day=1)),
                "物料类别": "原料",
                "物料名称": "葡萄糖",
                "规格": "25kg/袋",
                "厂内批号": "2608001",
                "入库数量": 500,
                "供应商": "某供应商",
            },
        ],
    }

    async def fake_load(page_key: str, force: bool) -> list[dict]:
        return rows_by_page[page_key]

    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        data = await service.get_dashboard_data("raw", detail=True)

    assert "detail" in data
    detail = data["detail"]
    assert {item["name"] for item in detail["safety_ok"]} == {"葡萄糖"}
    assert {item["name"] for item in detail["safety_low"]} == {"酵母粉"}
    assert detail["pending"][0]["batch"] == "2608001"
    assert detail["month_inbound"][0]["quantity"] == 500

    # 不传 detail 且无缓存时不附加明细（新建实例避免缓存命中）
    fresh = await _make_service()
    with patch.object(
        WarehouseService, "_load_page_rows", new=AsyncMock(side_effect=fake_load)
    ):
        plain = await fresh.get_dashboard_data("raw")
    assert "detail" not in plain
