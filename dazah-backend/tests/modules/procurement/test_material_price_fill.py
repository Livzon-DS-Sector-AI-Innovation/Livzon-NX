"""Spreadsheet price fill: column detection, matching and workbook writing."""

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from app.modules.procurement import price_table_fill


def build_workbook(
    headers: list[str],
    rows: list[list[object]],
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class FakePriceRepository:
    def __init__(self, session=None) -> None:
        self.session = session

    async def latest_price_by_codes(self, codes):
        mapping = {
            "51069308": {
                "material_name": "隔膜垫,DN15卫生级",
                "unit": "片",
                "data_year": 2025,
                "avg_price": Decimal("34.12"),
            }
        }
        return {code: mapping[code] for code in codes if code in mapping}

    async def search_by_name(self, keyword, *, limit=8):
        if "隔膜垫" in keyword:
            return [
                ("51069308", "隔膜垫,DN15卫生级", "片", Decimal("34.12")),
                ("51015318", "隔膜垫,DN50/卫生级", "片", Decimal("83.65")),
            ]
        return []


@pytest.fixture(autouse=True)
def fake_sources(monkeypatch):
    from datetime import date

    from app.modules.procurement.price_live_source import LivePriceRecord

    monkeypatch.setattr(
        price_table_fill,
        "MaterialPriceRepository",
        FakePriceRepository,
    )

    async def fake_live(db, *, material_codes=None, keyword=None, limit=None):
        records = [
            LivePriceRecord(
                material_code="51069308",
                material_name="隔膜垫,DN15卫生级",
                unit="片",
                unit_price=Decimal("29.00"),
                quantity=Decimal("5"),
                amount=Decimal("145.00"),
                supplier_name="衡水兴合",
                department="101-2 车间",
                batch_no="26-101-2/07-08",
                data_date=date(2026, 7, 7),
            )
        ]
        if material_codes:
            records = [r for r in records if r.material_code in material_codes]
        return records

    monkeypatch.setattr(price_table_fill, "list_live_prices", fake_live)


def test_detect_columns_uses_header_keywords():
    content = build_workbook(
        ["序号", "物料编码", "物料名称", "数量", "单价（元）", "备注"],
        [[1, "51069308", "隔膜垫,DN15卫生级", 10, None, ""]],
    )
    workbook = load_workbook(BytesIO(content))
    worksheet = workbook.active
    mapping = price_table_fill.detect_columns(worksheet)
    assert mapping.header_row == 1
    assert mapping.code_column == 2
    assert mapping.name_column == 3
    assert mapping.quantity_column == 4
    assert mapping.price_column == 5
    assert mapping.fillable is True


def test_detect_columns_falls_back_to_data_shape():
    content = build_workbook(
        ["A", "B", "C"],
        [
            ["51069308", "隔膜垫,DN15卫生级", 12.5],
            ["51015318", "隔膜垫,DN50/卫生级", 80],
            ["51014401", "不锈钢法兰球阀", 56.8],
        ],
    )
    workbook = load_workbook(BytesIO(content))
    mapping = price_table_fill.detect_columns(workbook.active)
    # 无表头关键词时：第一列像编码，最长文本列作名称；价格列识别不到
    assert mapping.code_column == 1
    assert mapping.name_column == 2
    assert mapping.fillable is False


@pytest.mark.anyio
async def test_preview_matches_code_name_and_reports_unmatched():
    content = build_workbook(
        ["序号", "物料编码", "物料名称", "单价"],
        [
            [1, "51069308", "隔膜垫,DN15卫生级", None],
            [2, "", "隔膜垫 DN50 卫生级", None],
            [3, "", "完全不存在的东西", None],
        ],
    )
    mapping, _headers, matches, total = (
        await price_table_fill.preview_fill(None, content)
    )
    assert total == 3
    assert mapping.code_column == 2
    assert mapping.price_column == 4
    by_row = {match.row_number: match for match in matches}
    # 编码命中，实时层优先
    assert by_row[2].source == "live"
    assert by_row[2].unit_price == Decimal("29.00")
    # 名称模糊命中
    assert by_row[3].source == "name_fuzzy"
    assert by_row[3].matched_code == "51015318"
    # 未匹配
    assert by_row[4].source == "unmatched"
    assert by_row[4].unit_price is None


@pytest.mark.anyio
async def test_fill_workbook_only_writes_blank_and_keeps_structure():
    content = build_workbook(
        ["序号", "物料编码", "物料名称", "单价", "备注"],
        [
            [1, "51069308", "隔膜垫,DN15卫生级", None, "保留我"],
            [2, "51069308", "隔膜垫,DN15卫生级", 99.5, "已有价"],
        ],
    )
    mapping, _headers, matches, _total = (
        await price_table_fill.preview_fill(None, content)
    )
    output, written = price_table_fill.fill_workbook(
        content,
        mapping=mapping,
        matches=matches,
        only_blank=True,
    )
    assert written == 1
    workbook = load_workbook(BytesIO(output))
    worksheet = workbook.active
    assert workbook.sheetnames == ["Sheet", "匹配说明"]
    # 空白单元格被填入实时价
    assert worksheet.cell(row=2, column=4).value == 29.0
    # 已有价格不被覆盖
    assert worksheet.cell(row=3, column=4).value == 99.5
    # 其他列保持原样
    assert worksheet.cell(row=2, column=5).value == "保留我"
    note = workbook["匹配说明"]
    assert note.cell(row=1, column=1).value == "行号"
    assert note.cell(row=2, column=6).value == 29.0


@pytest.mark.anyio
async def test_fill_workbook_can_overwrite_when_requested():
    content = build_workbook(
        ["物料编码", "单价"],
        [["51069308", 99.5]],
    )
    mapping, _headers, matches, _total = (
        await price_table_fill.preview_fill(None, content)
    )
    output, written = price_table_fill.fill_workbook(
        content,
        mapping=mapping,
        matches=matches,
        only_blank=False,
    )
    assert written == 1
    worksheet = load_workbook(BytesIO(output)).active
    assert worksheet.cell(row=2, column=2).value == 29.0


def test_fill_workbook_rejects_missing_price_column():
    content = build_workbook(["物料编码", "数量"], [["51069308", 1]])
    mapping = price_table_fill.detect_columns(
        load_workbook(BytesIO(content)).active
    )
    with pytest.raises(ValueError):
        price_table_fill.fill_workbook(
            content,
            mapping=mapping,
            matches=[],
        )
