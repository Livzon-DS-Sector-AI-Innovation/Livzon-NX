"""Audit the approved XLSX files as one timeline without connecting to a database.

uv run python -m scripts.audit_energy_continuity --output <json> <four xlsx files>
"""

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from pydantic import JsonValue

from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_source_workbook import SourceWorkbook, source_period
from scripts.energy_reference_continuity import (
    ContinuousMonthView,
    ContinuousWorkbook,
    WorkbookSnapshot,
)

_SOURCES = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "tests/modules/energy/fixtures/reference_sources.json"
    ).read_text(encoding="utf-8")
)


def audit(paths: list[Path]) -> dict[str, JsonValue]:
    snapshots = []
    for path in paths:
        content = path.read_bytes()
        payload = inspect_xlsx(content, 2026)
        period = source_period(payload)
        if period is None:
            raise ValueError("原表月份无法识别")
        specification = _SOURCES.get(f"{period[0]}-{period[1]:02}")
        digest = hashlib.sha256(content).hexdigest()
        if specification is None or specification["sha256"] != digest:
            raise ValueError("文件不是本次指定的四份原表之一")
        snapshots.append(
            WorkbookSnapshot(
                period,
                path.name,
                digest,
                "",
                payload,
                SourceWorkbook.from_payload(payload, period=period),
            )
        )
    if {item.period for item in snapshots} != {
        (2026, month) for month in [7, 8, 9, 10]
    } or len(snapshots) != 4:
        raise ValueError("必须提供四份不同月份的完整原表")
    snapshots.sort(key=lambda item: item.period)
    continuous = ContinuousWorkbook(snapshots)
    conflicts: list[JsonValue] = []
    gaps: list[JsonValue] = []
    decreases: list[JsonValue] = []
    deduplicated, filled = 0, 0
    for identity in sorted(continuous.required):
        missing: list[JsonValue] = []
        for offset in range(123):
            day = date(2026, 7, 1) + timedelta(days=offset)
            key = continuous.address(identity, day)
            cell = continuous.result(*key)
            observations = continuous.observations.get(key, [])
            populated = [
                item for item in observations if item.raw is not None and item.raw != ""
            ]
            filled += cell.provenance.get("continuity_filled") is True
            if cell.status == "complete":
                deduplicated += max(0, len(populated) - 1)
            elif cell.status == "pending_review":
                conflicts.append(
                    {
                        "date": str(day),
                        "sheet": identity[0],
                        "field": continuous.labels[identity],
                        "sources": cell.provenance["continuity_candidates"],
                    }
                )
            elif cell.status == "missing_reading":
                missing.append(str(day))
            if identity[0].endswith("码") and cell.value is not None:
                before = continuous.result(
                    *continuous.address(identity, day - timedelta(days=1))
                )
                if before.value is not None and cell.value < before.value:
                    decreases.append(
                        {
                            "date": str(day),
                            "sheet": identity[0],
                            "field": continuous.labels[identity],
                            "before": str(before.value),
                            "after": str(cell.value),
                        }
                    )
        if missing:
            gaps.append(
                {
                    "sheet": identity[0],
                    "field": continuous.labels[identity],
                    "dates": missing,
                }
            )
    monthly: list[JsonValue] = []
    for snapshot in snapshots:
        view = ContinuousMonthView(snapshot, continuous)
        source = snapshot.book.sheets[snapshot.book.resolve_sheet("日总量")]
        days = (
            date(2026, snapshot.period[1] + 1, 1) - date(2026, snapshot.period[1], 1)
        ).days
        metrics: list[JsonValue] = []
        for column in [4, 6, 7, 8, 9, 10]:
            cells = [
                view.cell_on("日总量", column, date(2026, snapshot.period[1], day))
                for day in range(1, days + 1)
            ]
            metrics.append(
                {
                    "field": source.headers[column - 1],
                    "statuses": dict(Counter(cell.status for cell in cells)),
                    "filled_days": sum(
                        cell.provenance.get("continuity_filled") is True
                        for cell in cells
                    ),
                    "unavailable_dates": [
                        str(date(2026, snapshot.period[1], index + 1))
                        for index, cell in enumerate(cells)
                        if cell.status != "complete"
                        or cell.value is None
                        or cell.value < 0
                    ],
                    "issues_by_date": [
                        {
                            "date": str(date(2026, snapshot.period[1], index + 1)),
                            "issues": cell.provenance["continuity_issues"],
                        }
                        for index, cell in enumerate(cells)
                        if cell.provenance.get("continuity_issues")
                    ],
                }
            )
        monthly.append({"month": snapshot.period[1], "metrics": metrics})
    return {
        "sources": [
            {"file": item.filename, "sha256": item.sha256} for item in snapshots
        ],
        "range": "2026-07-01/2026-10-31",
        "calendar_days": 123,
        "deduplicated_input_observations": deduplicated,
        "filled_input_cells": filled,
        "input_conflicts": conflicts,
        "missing_inputs": gaps,
        "counter_decreases_requiring_review": decreases,
        "date_issues": list(continuous.date_issues),
        "monthly_metrics": monthly,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("files", type=Path, nargs=4)
    args = parser.parse_args()
    result = audit(args.files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    conflicts = result["input_conflicts"]
    decreases = result["counter_decreases_requiring_review"]
    print(
        json.dumps(
            {
                "calendar_days": 123,
                "deduplicated": result["deduplicated_input_observations"],
                "filled_inputs": result["filled_input_cells"],
                "conflicts": len(conflicts) if isinstance(conflicts, list) else 0,
                "counter_decreases": len(decreases)
                if isinstance(decreases, list)
                else 0,
            },
            ensure_ascii=False,
        )
    )
