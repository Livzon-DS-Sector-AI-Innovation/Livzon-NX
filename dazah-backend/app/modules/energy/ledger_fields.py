"""Stable business identities and the physical columns of each source workbook."""

import hashlib
import re
from collections import Counter
from typing import TYPE_CHECKING

from openpyxl.utils.cell import get_column_letter
from pydantic import JsonValue

from app.modules.energy.ledger_source_policy import (
    SOURCE_CATEGORIES,
    input_column_allowed,
)

if TYPE_CHECKING:
    from app.modules.energy.ledger_schemas import MeterDefinition, RuleDefinition


def canonical_sheet(name: str) -> str:
    return "日总量" if name == "日用量" else name


def normalize_label(label: str) -> str:
    value = re.sub(r"\s+", "", label).replace("（", "(").replace("）", ")")
    return value.replace("(-5℃)", "-5℃")


def business_key(sheet: str, label: str, duplicate_column: int | None = None) -> str:
    identity = f"{canonical_sheet(sheet)}|{normalize_label(label)}"
    if duplicate_column is not None:
        identity += f"|column:{duplicate_column}"
    return "field_" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def definition_label(definition: "MeterDefinition | RuleDefinition") -> str:
    return re.sub(r"〔[A-Z]+列〕$", "", definition.name.rsplit("·", 1)[-1]).strip()


def definition_key(definition: "MeterDefinition | RuleDefinition") -> str:
    duplicate = bool(re.search(r"〔[A-Z]+列〕$", definition.name))
    return business_key(
        definition.source_sheet,
        definition_label(definition),
        definition.source_column if duplicate else None,
    )


def build_field_mappings(payload: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Link business fields to exact source columns; formulas stay in source_grid."""
    sheets = payload.get("sheets")
    if not isinstance(sheets, list):
        return []
    result: list[dict[str, JsonValue]] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        name, headers, grid = (
            sheet.get("name"),
            sheet.get("headers"),
            sheet.get("source_grid", []),
        )
        if (
            not isinstance(name, str)
            or not isinstance(headers, list)
            or not isinstance(grid, list)
        ):
            continue
        labels = [normalize_label(str(label or "")) for label in headers]
        counts = Counter(labels)
        computed: dict[int, list[JsonValue]] = {}
        for row_index, row in enumerate(grid, 1):
            if not isinstance(row, list):
                continue
            for column, value in enumerate(row, 1):
                if isinstance(value, str) and value.startswith("="):
                    computed.setdefault(column, []).append(
                        f"{get_column_letter(column)}{row_index}"
                    )
        for column, label in enumerate(labels, 1):
            if column < 2 or (not label and column not in computed):
                continue
            unnamed = not label
            if unnamed:
                label = f"未命名计算列({get_column_letter(column)})"
            detached = name in {"冰水码", "循环水码"} and any(
                not labels[index] and not labels[index + 1]
                for index in range(1, column - 2)
            )
            excluded = detached or "大罐数量" in label
            result.append(
                {
                    "business_key": business_key(
                        name, label, column if counts[label] > 1 else None
                    ),
                    "business_sheet": canonical_sheet(name),
                    "business_name": label,
                    "source_sheet": name,
                    "source_column": column,
                    "source_column_letter": get_column_letter(column),
                    "source_label": str(headers[column - 1] or ""),
                    "kind": "excluded"
                    if excluded
                    else "reading"
                    if name in SOURCE_CATEGORIES
                    and input_column_allowed(name, headers, column, set(computed))
                    else "calculated"
                    if column in computed
                    else "literal",
                    "status": "excluded"
                    if excluded
                    else "missing_label"
                    if unnamed
                    else "duplicate_label"
                    if counts[label] > 1
                    else "mapped",
                    "reason": "空白分隔区后的字段须核对"
                    if detached
                    else "大罐数量不属于能源指标"
                    if excluded
                    else "原表无表头，保留公式，字段名称须核对"
                    if unnamed
                    else "同名表计按原列区分，移列须核对"
                    if counts[label] > 1
                    else "",
                    "formula_cells": computed.get(column, []),
                }
            )
    return result


def find_field(
    mappings: list[dict[str, JsonValue]], definition: "MeterDefinition | RuleDefinition"
) -> dict[str, JsonValue] | None:
    matches = [
        item
        for item in mappings
        if item.get("business_sheet") == canonical_sheet(definition.source_sheet)
        and item.get("business_name") == normalize_label(definition_label(definition))
        and item.get("kind") != "excluded"
    ]
    if len(matches) == 1:
        return matches[0]
    from app.modules.energy.ledger_schemas import MeterDefinition

    if not matches and (
        isinstance(definition, MeterDefinition)
        or "·" not in definition.name
        or bool(re.search(r"原表[A-Z]+列无表头", definition.name))
    ):
        # Manually named legacy configurations explicitly bound a column.
        return next(
            (
                item
                for item in mappings
                if item.get("source_sheet") == definition.source_sheet
                and item.get("source_column") == definition.source_column
                and item.get("kind") != "excluded"
                and (
                    not re.search(r"原表[A-Z]+列无表头", definition.name)
                    or item.get("status") == "missing_label"
                )
            ),
            None,
        )
    # Duplicate names are distinct meters; a column move cannot be guessed.
    return next(
        (
            item
            for item in matches
            if item.get("source_column") == definition.source_column
        ),
        None,
    )


def mapping_matches_column(
    mappings: list[dict[str, JsonValue]],
    definition: "MeterDefinition | RuleDefinition",
    sheet: str,
    column: int,
) -> bool:
    field = find_field(mappings, definition)
    return (
        field is not None
        and field.get("source_sheet") == sheet
        and field.get("source_column") == column
    )
