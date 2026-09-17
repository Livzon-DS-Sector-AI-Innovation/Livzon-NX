"""排产 Excel 存档：workbook 解析与序列化单测。"""

from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

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
async def test_parse_workbook_prefers_visible_sheet_over_hidden() -> None:
    """历史 Sheet 隐藏保留的多周期文件：解析首个可见工作表，而非隐藏的首表。"""
    wb = openpyxl.Workbook()
    hidden = wb.active
    hidden.title = "历史排产（隐藏）"
    hidden["A1"] = "不应被解析"
    hidden.sheet_state = "hidden"
    visible = wb.create_sheet("多拉排产2026.09.05")
    visible["A1"] = "2026年9月排产计划"
    buffer = BytesIO()
    wb.save(buffer)
    parsed = schedule_excel_service.parse_workbook_bytes(buffer.getvalue())

    assert parsed["sheet_name"] == "多拉排产2026.09.05"
    assert parsed["rows"][0][0] == "2026年9月排产计划"


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


# ═══════════ 重复存档合并：冻结历史日列（merge_schedule_rows） ═══════════


def _schedule_rows(dump_row: list, ferm_time_row: list, seed_row: list) -> list[list]:
    """单块排产表（8/27~8/30），放罐/移种/种子三行可定制。"""
    return [
        ["2026年08月27日～2026年09月26日", "", "", "", ""],
        ["", "日期", 27, 28, 29, 30],
        ["时间", "罐号", "", "", "", ""],
        ["种子罐", *seed_row],
        ["罐号", "", "202A", "201A", "202A", "201A"],
        ["接种时间", "", "20:00", "20:00", "20:00", "20:00"],
        ["发酵罐", "", "FA-M0", "FA-M1", "FA-M2", "FA-M3"],
        ["罐号", "", "302A", "303A", "304A", "302A"],
        ["移种时间", *ferm_time_row],
        ["放罐", *dump_row],
        ["罐号", "", "302A", "", "", "302A"],
        ["放罐时间", "", "10:00", "", "", "10:00"],
        ["备注", "本周期共放罐2批", "", "", "", ""],
    ]


def test_merge_preserves_past_days_and_takes_new_today_onwards() -> None:
    """今天之前的日列沿用旧存档；当天及以后采用新文件。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_preserve_past,
    )

    today = date(2026, 8, 29)
    old_rows = _schedule_rows(
        dump_row=["", "FA-PREV", "", "", "FA-M0"],
        ferm_time_row=["", "21:00", "21:00", "21:00", "21:00"],
        seed_row=["", "FA-S0", "FA-S1", "FA-S2", "FA-S3"],
    )
    # 新文件：漏带 8/27 放罐 FA-PREV；当天(8/29)换种子批号；8/30 移种改 22:00
    new_rows = _schedule_rows(
        dump_row=["", "", "", "", "FA-M0"],
        ferm_time_row=["", "21:00", "21:00", "21:00", "22:00"],
        seed_row=["", "FA-S0", "FA-S1", "FA-S2X", "FA-S3"],
    )

    merged = merge_schedule_rows_preserve_past(new_rows, old_rows, today)

    # 8/27（过去）：新文件漏带的放罐批号从旧存档回填
    assert merged[9][2] == "FA-PREV"
    # 8/29（当天）：采用新文件
    assert merged[3][4] == "FA-S2X"
    # 8/30（未来）：采用新文件
    assert merged[8][5] == "22:00"
    # 入参不被修改
    assert new_rows[9][2] == ""
    assert old_rows[8][5] == "21:00"


def test_merge_keeps_new_file_without_matching_old_block() -> None:
    """旧存档无同周期块（首次存档/换月表）时保持新文件原样。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_preserve_past,
    )

    today = date(2026, 8, 29)
    new_rows = _schedule_rows(
        dump_row=["", "FA-PREV", "", "", "FA-M0"],
        ferm_time_row=["", "21:00", "21:00", "21:00", "21:00"],
        seed_row=["", "FA-S0", "FA-S1", "FA-S2", "FA-S3"],
    )
    old_rows = [["与排产无关的表", "", ""]]

    merged = merge_schedule_rows_preserve_past(new_rows, old_rows, today)

    assert merged == new_rows


# ═══════ 按产品适配合并：DR/MC/他汀块识别与历史修正 ═══════


def _dr_schedule_rows(ferm_tank_row: list) -> list[list]:
    """单块 DR 排产表（2026-04 自然月 4 列），发酵罐号行可定制。

    行偏移对齐 DR 解析：+1 日期 +5 进罐批号 +6 发酵罐号 +7 放罐批号
    +8 放罐罐号 +9 培养周期 +10 备注。DR-26013 场景：进罐写在 B403、
    放罐写在 B404（历史真实事故：罐号不一致卡死罐状态板）。
    """
    return [
        ["102车间2026年04月份多拉计划（04.05）"],
        ["日期", 5, 6, 18, 19],
        [],
        [],
        [],
        ["", "DR-26013", "", "", ""],
        ferm_tank_row,
        ["", "", "", "DR-26013", ""],
        ["", "", "", "B404", ""],
        ["", "", "", "300h", ""],
        ["备注", ""],
    ]


def test_merge_dr_freezes_history_tank_change() -> None:
    """DR-26013 场景：重传表把 4/5 进罐罐号 B403 改成 B404，冻结后保留 B403。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    old_rows = _dr_schedule_rows(["", "B403", "", "", ""])
    new_rows = _dr_schedule_rows(["", "B404", "", "", ""])

    merged, report = merge_schedule_rows_for_product(
        new_rows, old_rows, date(2026, 9, 17), "DR"
    )

    assert report["recognized"] is True
    assert report["matched_blocks"] == 1
    assert report["frozen_columns"] == 4
    assert report["corrected"] is False
    # 历史列冻结：进罐罐号沿用旧存档
    assert merged[6][1] == "B403"
    assert {
        "block": "2026-04",
        "row": "发酵罐号",
        "date": "2026-04-05",
        "column": 1,
        "old": "B403",
        "new": "B404",
    } in report["discarded_changes"]
    # 入参不被修改
    assert new_rows[6][1] == "B404"


def test_merge_dr_history_fix_takes_new_values() -> None:
    """显式历史修正（freeze_past=False）：以新文件为准，差异照常记录。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    old_rows = _dr_schedule_rows(["", "B403", "", "", ""])
    new_rows = _dr_schedule_rows(["", "B404", "", "", ""])

    merged, report = merge_schedule_rows_for_product(
        new_rows, old_rows, date(2026, 9, 17), "DR", freeze_past=False
    )

    assert report["corrected"] is True
    assert merged[6][1] == "B404"
    change = next(
        c for c in report["discarded_changes"] if c["date"] == "2026-04-05"
    )
    assert (change["old"], change["new"]) == ("B403", "B404")


def test_merge_history_fix_without_changes_not_corrected() -> None:
    """修正模式但新文件与原存档无历史差异：corrected=False，不产生空修正。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    rows = _dr_schedule_rows(["", "B403", "", "", ""])

    merged, report = merge_schedule_rows_for_product(
        rows, rows, date(2026, 9, 17), "DR", freeze_past=False
    )

    assert report["recognized"] is True
    assert report["discarded_changes"] == []
    assert report["corrected"] is False


def test_merge_reports_unrecognized_sheet() -> None:
    """新文件一个周期块都识别不出时 recognized=False，行原样返回。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    old_rows = _dr_schedule_rows(["", "B403", "", "", ""])

    merged, report = merge_schedule_rows_for_product(
        [["随便一张没有周期块的表"]], old_rows, date(2026, 9, 17), "DR"
    )

    assert report["recognized"] is False
    assert report["matched_blocks"] == 0
    assert merged == [["随便一张没有周期块的表"]]


def _mp_schedule_rows(ferm_tank_row: list) -> list[list]:
    """单块 MC 排产表（2026-08 两列）：+1 序号 +8 进罐批号 +9 发酵罐号。"""
    rows: list[list] = [[] for _ in range(19)]
    rows[0] = ["2026年08月MC放罐计划"]
    rows[1] = ["序号", 1, 2]
    rows[8] = ["", "MC-26246", "MC-26247"]
    rows[9] = ferm_tank_row
    rows[18] = ["备注"]
    return rows


def test_merge_mc_freezes_past_columns() -> None:
    """MC 表历史列改动同样被冻结（原实现只认 FA 格式，此处为回归）。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    old_rows = _mp_schedule_rows(["", "301A", "302B"])
    new_rows = _mp_schedule_rows(["", "301A", "303B"])

    merged, report = merge_schedule_rows_for_product(
        new_rows, old_rows, date(2026, 9, 17), "MC"
    )

    assert report["recognized"] is True
    assert report["frozen_columns"] == 2
    assert merged[9][2] == "302B"
    assert {
        "block": "2026-08",
        "row": "发酵罐号",
        "date": "2026-08-02",
        "column": 2,
        "old": "302B",
        "new": "303B",
    } in report["discarded_changes"]


def _statin_schedule_rows(ferm_tank_row: list) -> list[list]:
    """单块他汀排产表（label 驱动布局，日期行标签在第 1 列）。"""
    return [
        ["2026年08月27日～2026年09月26日 103发酵洛伐计划"],
        ["", "日期", 5, 6],
        ["种子罐", "", "LV-26001", "LV-26002"],
        ["接种量", "", 100, 100],
        ["发酵罐", "", "LV-26001", "LV-26002"],
        ferm_tank_row,
        ["移种", "", "14:00", "14:00"],
        ["放罐", "", "LV-26001", "LV-26002"],
        ["放罐时间", "", "08:00", "08:00"],
    ]


def test_merge_statin_freezes_past_columns() -> None:
    """他汀（LV）表：label 驱动块同样按日期冻结历史列。"""
    from app.modules.production.fermentation_board_service import (
        merge_schedule_rows_for_product,
    )

    old_rows = _statin_schedule_rows(["罐号", "", "301B", "302B"])
    new_rows = _statin_schedule_rows(["罐号", "", "301B", "303B"])

    merged, report = merge_schedule_rows_for_product(
        new_rows, old_rows, date(2026, 9, 17), "LV"
    )

    assert report["recognized"] is True
    assert report["frozen_columns"] == 2
    assert merged[5][3] == "302B"
    change = next(c for c in report["discarded_changes"] if c["old"])
    assert (change["old"], change["new"]) == ("302B", "303B")
    assert change["row"] == "罐号"


# ═══════════ create_archive：合并编排 / 拒绝 / 修正原因校验 ═══════════


def _patch_latest_archive(
    monkeypatch: Any, rows: list[list]
) -> AsyncMock:
    from app.modules.production import fermentation_board_service

    latest_loader = AsyncMock(return_value=SimpleNamespace(rows=rows))
    monkeypatch.setattr(
        fermentation_board_service, "load_latest_archive", latest_loader
    )
    return latest_loader


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = Mock()
    return session


@pytest.mark.anyio
async def test_create_archive_merges_with_latest_and_reports(
    monkeypatch: Any,
) -> None:
    """create_archive 用最新存档冻结历史并返回合并报告。"""
    _patch_latest_archive(
        monkeypatch, _dr_schedule_rows(["", "B403", "", "", ""])
    )
    new_rows = _dr_schedule_rows(["", "B404", "", "", ""])

    archive, report = await schedule_excel_service.create_archive(
        _make_session(),
        product_code="DR",
        file_name="多拉.xlsx",
        sheet_name="多拉排产",
        original_path="schedule_excel/dr.xlsx",
        rows=new_rows,
        merges=[],
        col_widths=[],
        row_count=len(new_rows),
        col_count=5,
    )

    assert report["recognized"] is True
    assert report["corrected"] is False
    assert report["discarded_changes"][0]["old"] == "B403"
    # 落库存档行是冻结后的合并结果
    assert archive.rows[6][1] == "B403"
    assert archive.product_code == "DR"


@pytest.mark.anyio
async def test_create_archive_rejects_unrecognized_sheet(
    monkeypatch: Any,
) -> None:
    """新文件识别不出周期块：拒绝存档并提示标准标题格式。"""
    _patch_latest_archive(
        monkeypatch, _dr_schedule_rows(["", "B403", "", "", ""])
    )

    with pytest.raises(ValueError, match="未能在新文件中识别任何排产周期块"):
        await schedule_excel_service.create_archive(
            _make_session(),
            product_code="DR",
            file_name="错表.xlsx",
            sheet_name="错表",
            original_path="schedule_excel/bad.xlsx",
            rows=[["与排产无关的表"]],
            merges=[],
            col_widths=[],
            row_count=1,
            col_count=1,
        )


@pytest.mark.anyio
async def test_create_archive_history_fix_requires_reason(
    monkeypatch: Any,
) -> None:
    """应用历史修正时原因必填。"""
    _patch_latest_archive(
        monkeypatch, _dr_schedule_rows(["", "B403", "", "", ""])
    )

    with pytest.raises(ValueError, match="修正原因"):
        await schedule_excel_service.create_archive(
            _make_session(),
            product_code="DR",
            file_name="多拉.xlsx",
            sheet_name="多拉排产",
            original_path="schedule_excel/dr.xlsx",
            rows=_dr_schedule_rows(["", "B404", "", "", ""]),
            merges=[],
            col_widths=[],
            row_count=11,
            col_count=5,
            history_fix=True,
            history_fix_reason="  ",
        )


@pytest.mark.anyio
async def test_create_archive_history_fix_applies_new_values(
    monkeypatch: Any,
) -> None:
    """history_fix + 原因：以新文件修正历史，报告标记 corrected。"""
    _patch_latest_archive(
        monkeypatch, _dr_schedule_rows(["", "B403", "", "", ""])
    )

    archive, report = await schedule_excel_service.create_archive(
        _make_session(),
        product_code="DR",
        file_name="多拉.xlsx",
        sheet_name="多拉排产",
        original_path="schedule_excel/dr.xlsx",
        rows=_dr_schedule_rows(["", "B404", "", "", ""]),
        merges=[],
        col_widths=[],
        row_count=11,
        col_count=5,
        history_fix=True,
        history_fix_reason="排产表笔误，实际进 B404",
    )

    assert report["corrected"] is True
    assert archive.rows[6][1] == "B404"
