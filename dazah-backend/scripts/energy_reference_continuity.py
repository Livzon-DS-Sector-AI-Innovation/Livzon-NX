"""Development-only continuity audit by business field and calendar date."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property

from openpyxl.utils.cell import column_index_from_string, get_column_letter
from pydantic import JsonValue

from app.modules.energy.ledger_fields import business_key, canonical_sheet
from app.modules.energy.ledger_schemas import WorkbookCell
from app.modules.energy.ledger_source_workbook import (
    ADDRESS,
    REFERENCE,
    SourceSheet,
    SourceWorkbook,
)

CellKey = tuple[str, str]


@dataclass
class WorkbookSnapshot:
    period: tuple[int, int]
    filename: str
    sha256: str
    batch_id: str
    payload: dict[str, JsonValue]
    book: SourceWorkbook

    @cached_property
    def indexed_dates(self) -> dict[str, dict[int, date]]:
        return {
            name: {row: day for day, row in sheet.dates.items()}
            for name, sheet in self.book.sheets.items()
        }

    @cached_property
    def listed_rows(self) -> dict[str, set[int]]:
        result: dict[str, set[int]] = {}
        sheets = self.payload.get("sheets", [])
        for item in sheets if isinstance(sheets, list) else []:
            if not isinstance(item, dict):
                continue
            entries = item.get("row_dates", [])
            result[str(item["name"])] = (
                {int(str(entry["row"])) for entry in entries if isinstance(entry, dict)}
                if isinstance(entries, list)
                else set()
            )
        return result

    def day_for(self, sheet: str, row: int) -> date | None:
        indexed = self.indexed_dates[sheet]
        if row in indexed:
            return indexed[row]
        # Never reinterpret an explicitly dated, ambiguous row as another date.
        if row in self.listed_rows.get(sheet, set()):
            return None
        # Month-end formulas reference the following one or two template rows.
        # Extend only a verified consecutive date index, never fill an internal gap.
        last = sorted(indexed)[-2:]
        if (
            len(last) == 2
            and max(self.listed_rows.get(sheet, set()), default=0) == last[1]
            and last[1] - last[0] == 1
            and indexed[last[1]] - indexed[last[0]] == timedelta(days=1)
            and 0 < row - last[1] <= 2
        ):
            return indexed[last[1]] + timedelta(days=row - last[1])
        return None


@dataclass
class SourceObservation:
    snapshot: WorkbookSnapshot
    sheet: str
    column: int
    row: int
    raw: JsonValue

    def evidence(self) -> dict[str, JsonValue]:
        return {
            "file": self.snapshot.filename,
            "sha256": self.snapshot.sha256,
            "batch_id": self.snapshot.batch_id,
            "sheet": self.sheet,
            "cell": f"{get_column_letter(self.column)}{self.row}",
            "raw": self.raw,
        }


class ContinuousWorkbook(SourceWorkbook):
    """One date index; source row numbers are translated before formula evaluation."""

    def __init__(self, snapshots: list[WorkbookSnapshot]) -> None:
        self.snapshots = snapshots
        self.start = min(
            day
            for item in snapshots
            for s in item.book.sheets.values()
            for day in s.dates
        )
        self.end = max(
            day
            for item in snapshots
            for s in item.book.sheets.values()
            for day in s.dates
        ) + timedelta(days=2)
        self.bindings: dict[tuple[str, str, int], tuple[str, str]] = {}
        self.fields: dict[tuple[str, str], int] = {}
        self.labels: dict[tuple[str, str], str] = {}
        self.required: set[tuple[str, str]] = set()
        self.observations: dict[CellKey, list[SourceObservation]] = defaultdict(list)
        self.identities: dict[CellKey, tuple[str, str, date]] = {}
        self.links: dict[CellKey, set[CellKey]] = defaultdict(set)
        self.active: dict[CellKey, JsonValue] = {}
        self.constants: dict[CellKey, JsonValue] = {}
        self.blocked: set[CellKey] = set()
        self.date_issues: list[str] = []
        for snapshot in snapshots:
            for sheet, source in snapshot.book.sheets.items():
                mapping = {
                    int(str(item["source_column"])): item
                    for item in snapshot.book.field_mappings
                    if item["source_sheet"] == sheet
                }
                width = max(len(source.headers), max(map(len, source.grid), default=0))
                for column in range(2, width + 1):
                    field = mapping.get(column)
                    label = (
                        source.headers[column - 1]
                        if column <= len(source.headers)
                        else ""
                    )
                    identity = (
                        canonical_sheet(sheet),
                        str(field["business_key"])
                        if field
                        else business_key(sheet, f"原表{get_column_letter(column)}列"),
                    )
                    self.bindings[snapshot.filename, sheet, column] = identity
                    if identity not in self.fields:
                        self.fields[identity] = (
                            sum(key[0] == identity[0] for key in self.fields) + 2
                        )
                        self.labels[identity] = label
                    for day, row in source.dates.items():
                        raw = (
                            source.grid[row - 1][column - 1]
                            if column <= len(source.grid[row - 1])
                            else None
                        )
                        address = self.address(identity, day)
                        self.observations[address].append(
                            SourceObservation(snapshot, sheet, column, row, raw)
                        )
                        if (
                            field
                            and field["kind"] == "reading"
                            and raw is not None
                            and raw != ""
                        ):
                            self.required.add(identity)
            raw_sheets = snapshot.payload.get("sheets", [])
            for item in raw_sheets if isinstance(raw_sheets, list) else []:
                entries = item.get("row_dates") if isinstance(item, dict) else None
                if isinstance(item, dict) and isinstance(entries, list):
                    counts = Counter(
                        str(entry.get("date"))
                        for entry in entries
                        if isinstance(entry, dict)
                    )
                    self.date_issues.extend(
                        f"{snapshot.filename} · {item['name']} · {day} "
                        "日期重复，未任取其中一行"
                        for day, count in counts.items()
                        if count > 1
                    )
        sheets: dict[str, SourceSheet] = {}
        dates = {
            self.start + timedelta(days=i): i + 2
            for i in range((self.end - self.start).days + 1)
        }
        for name in {key[0] for key in self.fields}:
            members = sorted(
                (key for key in self.fields if key[0] == name),
                key=lambda key: self.fields[key],
            )
            headers = ["日期", *[self.labels[key] for key in members]]
            sheets[name] = SourceSheet(headers, [list(headers)], dates)
            for identity in members:
                for day in dates:
                    self.identities[self.address(identity, day)] = (*identity, day)
        super().__init__(sheets)

    def address(self, identity: tuple[str, str], day: date) -> CellKey:
        return identity[
            0
        ], f"{get_column_letter(self.fields[identity])}{(day - self.start).days + 2}"

    def rewrite(self, observation: SourceObservation) -> JsonValue:
        raw = observation.raw
        if not isinstance(raw, str) or not raw.startswith("="):
            return raw
        refs: dict[str, tuple[str, str]] = {}
        body = raw[1:]

        def tokenize(match: re.Match[str]) -> str:
            sheet = match["sheet"] or observation.sheet
            if (
                not match["sheet"]
                and body[: match.start()].rstrip().endswith(":")
                and refs
            ):
                sheet = refs[f"ref_{len(refs) - 1}"][0]
            if sheet.startswith("'"):
                sheet = sheet[1:-1].replace("''", "'")
            token = f"ref_{len(refs)}"
            refs[token] = sheet, match["column"] + match["row"]
            return token

        expression = REFERENCE.sub(tokenize, body)

        def expand(match: re.Match[str]) -> str:
            left, right = refs[match[1]], refs[match[2]]
            a, b = ADDRESS.fullmatch(left[1]), ADDRESS.fullmatch(right[1])
            if left[0] != right[0] or a is None or b is None:
                raise ValueError("原表范围引用无效")
            size = (int(b[2]) - int(a[2]) + 1) * (
                column_index_from_string(b[1]) - column_index_from_string(a[1]) + 1
            )
            if not 1 <= size <= 1000:
                raise ValueError("原表范围引用超限或倒置")
            result = []
            for row in range(int(a[2]), int(b[2]) + 1):
                for column in range(
                    column_index_from_string(a[1]), column_index_from_string(b[1]) + 1
                ):
                    token = f"ref_{len(refs)}"
                    refs[token] = left[0], f"{get_column_letter(column)}{row}"
                    result.append(token)
            return ",".join(result)

        expression = re.sub(r"(ref_\d+):(ref_\d+)", expand, expression)

        def translate(match: re.Match[str]) -> str:
            sheet, address = refs[match[0]]
            sheet = observation.snapshot.book.resolve_sheet(sheet)
            source = observation.snapshot.book.sheets.get(sheet)
            parts = ADDRESS.fullmatch(address)
            if source is None or parts is None:
                return f"'{sheet}'!{address}"
            row, column = int(parts[2]), column_index_from_string(parts[1])
            identity = self.bindings.get((observation.snapshot.filename, sheet, column))
            day = observation.snapshot.day_for(sheet, row)
            if identity and day is not None:
                target = self.address(identity, day)
                return f"'{target[0]}'!{target[1]}"
            key = "__原表固定单元格", f"A{len(self.constants) + 1}"
            self.constants[key] = (
                source.grid[row - 1][column - 1]
                if row <= len(source.grid) and column <= len(source.grid[row - 1])
                else None
            )
            if row > 1:
                self.blocked.add(key)
            return f"'{key[0]}'!{key[1]}"

        return "=" + re.sub(r"ref_\d+", translate, expression)

    def _raw(self, sheet: str, address: str) -> JsonValue:
        key = sheet, address
        if key in self.active:
            return self.active[key]
        if key in self.constants:
            return self.constants[key]
        if key in self.identities:
            return None
        return super()._raw(sheet, address)

    def result(
        self, sheet: str, address: str, stack: tuple[CellKey, ...] = ()
    ) -> WorkbookCell:
        key = sheet, address
        if stack:
            self.links[stack[-1]].add(key)
        if key in stack or len(stack) >= 64:
            return WorkbookCell(status="source_formula_cycle")
        if key in self._cache:
            return self._cache[key].model_copy(deep=True)
        if key in self.blocked:
            return WorkbookCell(status="source_date_conflict")
        identity = self.identities.get(key)
        if identity is None:
            return super().result(sheet, address, stack)
        observations = self.observations.get(key, [])
        populated = [
            item for item in observations if item.raw is not None and item.raw != ""
        ]
        choices: dict[str, JsonValue] = {}
        results: list[WorkbookCell] = []
        for item in populated:
            try:
                raw = self.rewrite(item)
            except ValueError:
                results.append(WorkbookCell(status="source_formula_error"))
                continue
            choices.setdefault(str(raw), raw)
        for raw in choices.values():
            self.active[key] = raw
            self._cache.pop(key, None)
            results.append(super().result(sheet, address, stack))
        self.active.pop(key, None)
        self._cache.pop(key, None)
        values = {item.value for item in results}
        if not results:
            cell = WorkbookCell(
                status="missing_reading"
                if identity[:2] in self.required
                else "source_blank"
            )
        elif len(values) > 1 or (
            len(results) > 1 and any(item.status != "complete" for item in results)
        ):
            cell = WorkbookCell(
                status="pending_review", calculated_value=results[0].calculated_value
            )
        else:
            cell = results[0]
        invalid_input = (
            identity[:2] in self.required and cell.status == "source_non_numeric"
        )
        if invalid_input:
            cell.status = "pending_review"
        dependencies = [
            self._cache[item] for item in self.links[key] if item in self._cache
        ]
        filled = bool(populated) and (
            len(populated) < len(observations)
            or not any(
                item.snapshot.period == (identity[2].year, identity[2].month)
                for item in populated
            )
        )
        issues: list[JsonValue] = []
        for dependency in dependencies:
            inherited = dependency.provenance.get("continuity_issues", [])
            for issue in inherited if isinstance(inherited, list) else []:
                if issue not in issues:
                    issues.append(issue)
        if cell.status == "pending_review" and not issues:
            issues.append(
                {
                    "reason": "原始读数不是有效数值"
                    if invalid_input
                    else "同日期同字段的来源值或公式结果不一致",
                    "candidates": [item.evidence() for item in populated],
                }
            )
        cell.provenance.update(
            continuous_field=identity[1],
            continuity_candidates=[item.evidence() for item in populated],
            continuity_filled=filled
            or any(item.provenance.get("continuity_filled") for item in dependencies),
            continuity_issues=issues,
            continuity_date_issues=list(self.date_issues),
        )
        self._cache[key] = cell
        return cell.model_copy(deep=True)


class ContinuousMonthView(SourceWorkbook):
    """Keep source column metadata while resolving values on the shared timeline."""

    def __init__(
        self, snapshot: WorkbookSnapshot, continuous: ContinuousWorkbook
    ) -> None:
        super().__init__(snapshot.book.sheets, snapshot.period)
        self.field_mappings = snapshot.book.field_mappings
        self.snapshot = snapshot
        self.continuous = continuous

    def cell_on(self, sheet: str, column: int, day: date) -> WorkbookCell:
        sheet = self.resolve_sheet(sheet)
        identity = self.continuous.bindings.get((self.snapshot.filename, sheet, column))
        if identity is None:
            return WorkbookCell(status="source_field_missing")
        target = self.continuous.address(identity, day)
        cell = self.continuous.result(*target)
        row = self.snapshot.book.sheets[sheet].dates.get(day)
        cell.provenance.update(
            source_sheet=sheet,
            source_cell=f"{get_column_letter(column)}{row}" if row else None,
        )
        return cell
