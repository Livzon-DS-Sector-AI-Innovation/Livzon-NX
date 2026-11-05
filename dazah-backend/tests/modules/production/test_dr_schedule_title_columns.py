"""DR 排产月份块标题列位置回归（2026-11-04 真实事故）。

个别月份块标题合并锚点从 B 列开始（存档后值在第 1 列），只查 row[0]
会漏块，导致看板判定当前周期无存档覆盖、概览不更新。
"""

from datetime import datetime

from app.modules.production.fermentation_board_service import (
    find_dr_period_block,
)


def _rows_with_title_at(title_col: int) -> list[list]:
    title_row = [""] * 4
    title_row[title_col] = "102车间2026年11月份多拉计划（10.08）"
    return [title_row, ["日期", 1, 2, 3, 4, 5]]


def test_title_in_first_column_finds_block() -> None:
    block = find_dr_period_block(
        _rows_with_title_at(0), datetime(2026, 11, 4, 12, 0)
    )
    assert block is not None
    assert block["label"] == "10月27日～11月26日"


def test_title_in_second_column_regression() -> None:
    block = find_dr_period_block(
        _rows_with_title_at(1), datetime(2026, 11, 4, 12, 0)
    )
    assert block is not None, "标题在第 1 列的月份块必须能被识别"
    assert block["start_row"] == 0


def test_title_in_third_column_finds_block() -> None:
    rows = [["", "", "", "102车间2026年12月份多拉计划（10.08）"]]
    block = find_dr_period_block(rows, datetime(2026, 12, 10, 12, 0))
    assert block is not None
