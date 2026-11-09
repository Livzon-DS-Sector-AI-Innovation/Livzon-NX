from datetime import date
from io import BytesIO

import openpyxl
import pytest

from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_source_workbook import SourceWorkbook
from scripts.energy_reference_continuity import (
    ContinuousMonthView,
    ContinuousWorkbook,
    WorkbookSnapshot,
)


def snapshot(
    month: int, rows: list[list[object]], moved: bool = False
) -> WorkbookSnapshot:
    book = openpyxl.Workbook()
    readings = book.active
    readings.title = "饮用水码"
    readings.append(["日期", "备用表", "主表"] if moved else ["日期", "主表", "备用表"])
    usage = book.create_sheet("饮用水量")
    usage.append(["日期", "用量"])
    column = "C" if moved else "B"
    for index, row in enumerate(rows, 2):
        readings.append([row[0], 999, row[1]] if moved else [*row, 999])
        usage.append(
            [row[0], f"=饮用水码!{column}{index + 1}-饮用水码!{column}{index}"]
        )
    output = BytesIO()
    book.save(output)
    payload = inspect_xlsx(output.getvalue(), 2026)
    payload["report_period"] = f"2026-{month:02}"
    return WorkbookSnapshot(
        (2026, month),
        f"{month}.xlsx",
        str(month),
        str(month),
        payload,
        SourceWorkbook.from_payload(payload, period=(2026, month)),
    )


def books(conflict: bool = False, moved: bool = False):
    july = snapshot(7, [[date(2026, 7, 30), 100], [date(2026, 7, 31), None]])
    august = snapshot(
        8,
        [
            [date(2026, 7, 30), 101 if conflict else 100],
            [date(2026, 7, 31), 130],
            [date(2026, 8, 1), 150],
            [date(2026, 8, 2), None],
        ],
        moved,
    )
    return july, august, ContinuousWorkbook([july, august])


@pytest.mark.parametrize("moved", [False, True])
def test_cross_file_next_day_reading_and_field_move_do_not_break_month_end(moved):
    july, _, continuous = books(moved=moved)
    view = ContinuousMonthView(july, continuous)
    assert view.cell_on("饮用水量", 2, date(2026, 7, 30)).value == 30
    last = view.cell_on("饮用水量", 2, date(2026, 7, 31))
    assert last.value == 20
    assert last.status == "complete"
    assert last.provenance["continuity_filled"] is True
    # Two matching copies of 7/30 still represent one observation, not 200.
    assert view.cell_on("饮用水码", 2, date(2026, 7, 30)).value == 100
    assert (
        len(
            view.cell_on("饮用水码", 2, date(2026, 7, 30)).provenance[
                "continuity_candidates"
            ]
        )
        == 2
    )


def test_conflicting_overlaps_preserve_both_values_and_propagate_to_usage():
    july, _, continuous = books(conflict=True)
    view = ContinuousMonthView(july, continuous)
    reading = view.cell_on("饮用水码", 2, date(2026, 7, 30))
    assert reading.value is None
    assert reading.status == "pending_review"
    assert {item["raw"] for item in reading.provenance["continuity_candidates"]} == {
        100,
        101,
    }
    usage = view.cell_on("饮用水量", 2, date(2026, 7, 30))
    assert usage.value is None
    assert usage.status == "pending_review"
    assert usage.provenance["continuity_issues"]


def test_missing_final_reading_is_not_zero_and_a_real_zero_is_retained():
    july, august, continuous = books()
    view = ContinuousMonthView(august, continuous)
    assert view.cell_on("饮用水量", 2, date(2026, 8, 1)).status == "missing_reading"
    assert view.cell_on("饮用水量", 2, date(2026, 8, 1)).value is None
    zero = snapshot(
        8, [[date(2026, 7, 30), 100], [date(2026, 7, 31), 0], [date(2026, 8, 1), 0]]
    )
    view = ContinuousMonthView(july, ContinuousWorkbook([july, zero]))
    assert view.cell_on("饮用水码", 2, date(2026, 7, 31)).value == 0


def test_does_not_bridge_an_actual_missing_calendar_day():
    july = snapshot(7, [[date(2026, 7, 30), 100], [date(2026, 7, 31), 130]])
    august = snapshot(8, [[date(2026, 8, 2), 180], [date(2026, 8, 3), 200]])
    view = ContinuousMonthView(july, ContinuousWorkbook([july, august]))
    assert view.cell_on("饮用水量", 2, date(2026, 7, 31)).value is None
    assert view.cell_on("饮用水量", 2, date(2026, 7, 31)).status == "missing_reading"


def test_range_sum_respects_field_moves_and_fixed_header_cells():
    july, august, _ = books(moved=True)
    for source in [july, august]:
        source.book.sheets["饮用水量"].grid[1][1] = "=SUM('饮用水码'!B1:C2)"
    view = ContinuousMonthView(july, ContinuousWorkbook([july, august]))
    assert view.cell_on("饮用水量", 2, date(2026, 7, 30)).value == 1099


def test_different_derived_results_are_not_silently_selected():
    july, august, _ = books()
    august.book.sheets["饮用水量"].grid[1][1] = 90
    view = ContinuousMonthView(july, ContinuousWorkbook([july, august]))
    cell = view.cell_on("饮用水量", 2, date(2026, 7, 30))
    assert cell.value is None
    assert cell.status == "pending_review"
    assert len(cell.provenance["continuity_candidates"]) == 2


def test_ambiguous_context_dates_are_not_reinterpreted_as_other_days():
    july = snapshot(7, [[date(2026, 7, 30), 100], [date(2026, 7, 31), 130]])
    august = snapshot(
        8,
        [
            [date(2026, 7, 31), 999],
            [date(2026, 7, 31), 998],
            [date(2026, 8, 1), 150],
            [date(2026, 8, 2), 160],
            [date(2026, 8, 3), 170],
        ],
    )
    merged = ContinuousWorkbook([july, august])
    view = ContinuousMonthView(july, merged)
    assert merged.date_issues
    assert august.day_for("饮用水码", 2) is None
    assert view.cell_on("饮用水码", 2, date(2026, 7, 31)).value == 130


def test_circular_formula_and_invalid_input_do_not_become_valid_zeros():
    july = snapshot(7, [[date(2026, 7, 30), "100"], [date(2026, 7, 31), "bad"]])
    july.book.sheets["饮用水量"].grid[1][1] = "=SUM(饮用水码!B2:B3)"
    july.book.sheets["饮用水量"].grid[2][1] = "=B3"
    view = ContinuousMonthView(july, ContinuousWorkbook([july]))
    assert view.cell_on("饮用水量", 2, date(2026, 7, 30)).status == "pending_review"
    assert (
        view.cell_on("饮用水量", 2, date(2026, 7, 31)).status == "source_formula_cycle"
    )
