"""price_live_source 的解析与查询测试。"""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.procurement.price_live_source import (
    _to_date,
    _to_decimal,
    list_live_prices,
    parse_row,
)


def _cells(**overrides) -> dict:
    cells = {
        "物料编号": "51069308",
        "物料说明": "隔膜垫,DN15卫生级",
        "单位": "片",
        "单价（元）": "29",
        "入库量": "5",
        "金额": "145",
        "供应商名称": "上海过滤器有限公司",
        "归属车间": "101-2 车间",
        "厂内批号": "26-101-2/07-08",
        "日期": 1767225600000,
    }
    cells.update(overrides)
    for key, value in list(cells.items()):
        if value is None:
            del cells[key]
    return cells


def test_parse_row_normalizes_fields() -> None:
    record = parse_row(_cells())
    assert record is not None
    assert record.material_code == "51069308"
    assert record.unit_price == Decimal("29")
    assert record.quantity == Decimal("5")
    assert record.supplier_name == "上海过滤器有限公司"
    assert record.department == "101-2 车间"
    assert record.data_date == date(2026, 1, 1)


def test_parse_row_computes_amount_when_missing() -> None:
    cells = _cells()
    del cells["金额"]
    record = parse_row(cells)
    assert record.amount == Decimal("145.00")


def test_parse_row_returns_none_without_code_or_price() -> None:
    assert parse_row(_cells(**{"物料编号": ""})) is None
    assert parse_row(_cells(**{"物料编号": "", "单价（元）": "10"})) is None
    assert parse_row(_cells(**{"单价（元）": "0"})) is None


def test_to_decimal_and_date_variants() -> None:
    assert _to_decimal("1,234.5") == Decimal("1234.5")
    assert _to_decimal(None) == Decimal("0")
    assert _to_decimal("abc") == Decimal("0")
    assert _to_date(1767225600000) == date(2026, 1, 1)
    assert _to_date("2026-01-02") == date(2026, 1, 2)
    assert _to_date("bad") is None
    assert _to_date(None) is None


async def test_list_live_prices_filters_sorts_and_requires_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_get_rows(
        session, *, page_key, search_text=None, field_values=None, limit=None
    ):
        captured["search_text"] = search_text
        captured["field_values"] = field_values
        rows = [
            _cells(物料编号="51069308", 日期=1767225600000),
            _cells(物料编号="51015318", 日期=1767312000000),
            _cells(物料编号="", 供应商名称="无编码行"),
        ]
        if search_text:
            rows = [
                r
                for r in rows
                if search_text
                in str(r.get("物料编号", "")) + str(r.get("物料说明", ""))
            ]
        return rows, None

    monkeypatch.setattr(
        "app.modules.procurement.price_live_source.get_material_page_rows",
        fake_get_rows,
    )

    records = await list_live_prices(
        None, material_codes={"51069308"}
    )
    assert captured["field_values"] == {"物料编号": ["51069308"]}
    assert [r.material_code for r in records] == ["51069308"]

    records_all = await list_live_prices(None, keyword="隔膜垫")
    assert captured["search_text"] == "隔膜垫"
    assert len(records_all) == 2
