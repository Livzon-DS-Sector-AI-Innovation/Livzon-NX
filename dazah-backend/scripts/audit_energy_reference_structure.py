"""Read-only development audit of input fields and source formula evidence."""

import argparse
import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl
from openpyxl.utils.cell import get_column_letter

from app.modules.energy.ledger_fields import build_field_mappings
from app.modules.energy.ledger_imports import inspect_xlsx
from app.modules.energy.ledger_source_policy import SOURCE_CATEGORIES
from app.modules.energy.ledger_source_workbook import (
    ADDRESS,
    SourceWorkbook,
    source_period,
)
from app.modules.energy.ledger_template import extract_template


def audit(path: Path, year: int) -> dict:
    payload = inspect_xlsx(path.read_bytes(), year)
    fields = build_field_mappings(payload)
    source = SourceWorkbook.from_payload(payload, period=source_period(payload))
    cached = openpyxl.load_workbook(path, data_only=True, read_only=True)
    cached_rows = {sheet.title: list(sheet.values) for sheet in cached}
    cached.close()
    formula_counts: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    formula_errors = []
    mismatches, date_references, missing_cache = [], [], 0
    raw_dates = {
        name: {row: day for day, row in sheet.dates.items()}
        for name, sheet in source.sheets.items()
    }
    for name, sheet in source.sheets.items():
        for day, row in sheet.dates.items():
            for column, raw in enumerate(sheet.grid[row - 1], 1):
                if not isinstance(raw, str) or not raw.startswith("="):
                    continue
                address = f"{get_column_letter(column)}{row}"
                formula_counts[name] += 1
                result = source.result(name, address)
                statuses[result.status] += 1
                if result.status != "complete":
                    formula_errors.append(
                        {
                            "sheet": name,
                            "cell": address,
                            "formula": raw,
                            "status": result.status,
                        }
                    )
                values = cached_rows[name]
                original = (
                    values[row - 1][column - 1]
                    if row <= len(values) and column <= len(values[row - 1])
                    else None
                )
                try:
                    number = Decimal(str(original))
                except InvalidOperation:
                    missing_cache += 1
                else:
                    if result.value is not None and abs(result.value - number) > max(
                        Decimal(".00001"), abs(number) * Decimal("1e-10")
                    ):
                        mismatches.append(
                            {
                                "sheet": name,
                                "cell": address,
                                "formula": raw,
                                "cached": str(number),
                                "calculated": str(result.value),
                            }
                        )
                if name in SOURCE_CATEGORIES:
                    continue
                for reference in result.provenance.get("sources", []):
                    if not isinstance(reference, dict):
                        continue
                    target = str(reference.get("sheet", ""))
                    address_ref = ADDRESS.fullmatch(str(reference.get("cell", "")))
                    if target == name or address_ref is None:
                        continue
                    ref_day = raw_dates.get(target, {}).get(int(address_ref[2]))
                    allowed = {day}
                    if target in SOURCE_CATEGORIES and target != "电量":
                        allowed.add(day + timedelta(days=1))
                    if ref_day is not None and ref_day not in allowed:
                        date_references.append(
                            {
                                "sheet": name,
                                "cell": address,
                                "date": day.isoformat(),
                                "formula": raw,
                                "reference_sheet": target,
                                "reference_date": ref_day.isoformat(),
                            }
                        )
    return {
        "file": path.name,
        "period": payload.get("report_period"),
        "source_warnings": payload.get("warnings"),
        "input_fields": {
            sheet: [field for field in fields if field["source_sheet"] == sheet]
            for sheet in SOURCE_CATEGORIES
        },
        "input_counts": {
            sheet: sum(
                field["source_sheet"] == sheet and field["kind"] == "reading"
                for field in fields
            )
            for sheet in SOURCE_CATEGORIES
        },
        "formula_counts": dict(formula_counts),
        "formula_statuses": dict(statuses),
        "formula_errors": formula_errors,
        "formula_cache_missing": missing_cache,
        "formula_cache_mismatches": mismatches,
        "date_reference_candidates": date_references,
        "template_issues": extract_template(payload).issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [audit(path, args.year) for path in args.files]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for result in results:
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "file",
                        "input_counts",
                        "formula_counts",
                        "formula_statuses",
                    )
                },
                ensure_ascii=False,
            )
        )
        print(
            json.dumps(
                {
                    key: len(result[key])
                    for key in (
                        "formula_cache_mismatches",
                        "date_reference_candidates",
                        "template_issues",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
