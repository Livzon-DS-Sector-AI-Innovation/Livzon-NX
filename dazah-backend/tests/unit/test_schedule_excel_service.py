"""排产 Excel 存档：workbook 解析与序列化单测。"""

from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO

import openpyxl  # type: ignore[import-untyped]
import pytest

from app.modules.production import schedule_excel_service


def _build_workbook_bytes() -> bytes:
    """构造测试 Excel：合并区、列宽、空行、日期、多 sheet、超 250 行。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "9月排产"
    ws.merge_cells("A1:B2")
    ws["A1"] = "2026年9月排产计划"
    ws["C1"] = 1
    ws.column_dimensions["C"].width = 30
    ws["A3"] = "班组"
    ws["B3"] = 5
    ws["C3"] = date(2026, 9, 8)
    ws["D3"] = datetime(2026, 9, 8, 10, 30)
    ws["E3"] = time(8, 0)
    # 大量行，验证不截断（> 250）
    for i in range(260):
        ws.cell(row=4 + i, column=1, value=f"行{i}")
    second = wb.create_sheet("第二个sheet")
    second["A1"] = "不应被解析"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.mark.anyio
async def test_parse_workbook_keeps_first_sheet_and_full_rows() -> None:
    parsed = schedule_excel_service.parse_workbook_bytes(_build_workbook_bytes())

    assert parsed["sheet_name"] == "9月排产"
    # 1 标题行 + 1 数据行 + 260 填充行（row 4..263），不截断
    assert parsed["row_count"] == 263
    assert len(parsed["rows"]) == 263
    assert parsed["rows"][-1][0] == "行259"

    # 合并单元格 0-based
    assert {"s": {"r": 0, "c": 0}, "e": {"r": 1, "c": 1}} in parsed["merges"]

    # 列宽：显式 30，其余默认 80
    widths = parsed["col_widths"]
    assert widths[2] == 30
    assert widths[0] == 80


@pytest.mark.anyio
async def test_parse_workbook_serializes_cells_readably() -> None:
    parsed = schedule_excel_service.parse_workbook_bytes(_build_workbook_bytes())

    assert parsed["rows"][0][0] == "2026年9月排产计划"  # 合并区左上角值
    assert parsed["rows"][2][1] == 5  # 数字原样
    assert parsed["rows"][2][2] == "2026-09-08"  # 日期转可读文本
    assert parsed["rows"][2][3] == "2026-09-08 10:30:00"  # 时间戳
    assert parsed["rows"][2][4] == "08:00:00"  # time
    # 空单元格统一空串
    assert parsed["rows"][1][2] == ""


def test_serialize_cell_edge_values() -> None:
    assert schedule_excel_service._serialize_cell(None) == ""
    assert schedule_excel_service._serialize_cell(0) == 0
    assert schedule_excel_service._serialize_cell(False) is False
    assert schedule_excel_service._serialize_cell("x") == "x"
    assert schedule_excel_service._serialize_cell(b"raw") == "b'raw'"


def test_serialize_archive_roundtrip_shape() -> None:
    archive = schedule_excel_service.parse_workbook_bytes(_build_workbook_bytes())
    payload = {
        "id": "id-1",
        "file_name": "排产.xlsx",
        "sheet_name": archive["sheet_name"],
        "original_path": "schedule_excel/x.xlsx",
        "rows": archive["rows"],
        "merges": archive["merges"],
        "col_widths": archive["col_widths"],
        "row_count": archive["row_count"],
        "col_count": archive["col_count"],
        "created_at": None,
        "updated_at": None,
    }
    # 列表摘要去掉大字段
    summary = {key: value for key, value in payload.items()}
    summary.pop("rows")
    summary.pop("merges")
    summary.pop("col_widths")
    assert "rows" not in summary
    assert "file_name" in summary
