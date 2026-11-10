"""Bounded evaluation of an imported source grid, preserving exact cell references.

Source formulas are historical reporting evidence. They do not become editable
meter points, change permission checks, or authorize writes to native readings.
"""

import ast
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext

from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import column_index_from_string, get_column_letter
from pydantic import JsonValue

from app.modules.energy.ledger_fields import (
    build_field_mappings,
    definition_key,
    definition_label,
    find_field,
)
from app.modules.energy.ledger_fields import (
    canonical_sheet as canonical_sheet,
)
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    RuleDefinition,
    UsageReview,
    WorkbookCell,
)

REFERENCE = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[\w.]+)!)?"
    r"\$?(?P<column>[A-Z]{1,3})\$?(?P<row>\d+)"
)
ADDRESS = re.compile(r"([A-Z]{1,3})([1-9]\d{0,3})")
MAX_CELLS = 100_000


def source_period(payload: dict[str, JsonValue]) -> tuple[int, int] | None:
    """Identify the report month, keeping adjacent dates as formula context."""
    explicit = payload.get("report_period")
    if isinstance(explicit, str) and re.fullmatch(r"\d{4}-\d{2}", explicit):
        year, month = (int(part) for part in explicit.split("-"))
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return year, month
    sheets = payload.get("sheets")
    counts: Counter[tuple[int, int]] = Counter()
    if isinstance(sheets, list):
        for sheet in sheets:
            rows = sheet.get("row_dates") if isinstance(sheet, dict) else None
            if not isinstance(rows, list):
                continue
            for item in rows:
                if isinstance(item, dict) and isinstance(item.get("date"), str):
                    day = date.fromisoformat(str(item["date"]))
                    counts[day.year, day.month] += 1
    return max(counts, key=lambda period: (counts[period], period)) if counts else None


@dataclass(frozen=True)
class SourceSheet:
    headers: list[str]
    grid: list[list[JsonValue]]
    dates: dict[date, int]


class SourceFormulaError(ValueError):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


class SourceWorkbook:
    def __init__(
        self, sheets: dict[str, SourceSheet], period: tuple[int, int] | None = None
    ) -> None:
        self.sheets = sheets
        self.period = period
        self._cache: dict[tuple[str, str], WorkbookCell] = {}
        self._readings: dict[tuple[str, str], tuple[Decimal, int]] = {}
        self._values: dict[tuple[str, str], Decimal] = {}
        self._required_inputs: set[tuple[str, int]] = set()
        self._reviews: dict[tuple[str, str], list[dict[str, JsonValue]]] = {}
        self.field_mappings: list[dict[str, JsonValue]] = []
        self._field_bindings: dict[
            tuple[str, str, int | None], dict[str, JsonValue] | None
        ] = {}

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, JsonValue],
        *,
        period: tuple[int, int] | None = None,
    ) -> "SourceWorkbook":
        source = payload.get("sheets")
        if not isinstance(source, list) or len(source) > 21:
            raise ValueError("原表快照最多包含21张工作表")
        sheets: dict[str, SourceSheet] = {}
        count = 0
        for item in source:
            if not isinstance(item, dict) or "source_grid" not in item:
                continue
            name, grid, headers = (
                item.get("name"),
                item.get("source_grid"),
                item.get("headers"),
            )
            if (
                not isinstance(name, str)
                or not name
                or name in sheets
                or not isinstance(grid, list)
                or len(grid) > 5000
                or not isinstance(headers, list)
                or len(headers) > 200
            ):
                raise ValueError("原表快照结构无效或包含重复表名")
            rows: list[list[JsonValue]] = []
            for row in grid:
                if not isinstance(row, list) or len(row) > 200:
                    raise ValueError("原表快照每行最多200列")
                if any(
                    isinstance(value, (dict, list))
                    or isinstance(value, str)
                    and len(value) > 4096
                    for value in row
                ):
                    raise ValueError("原表单元格不是有效的标量")
                count += len(row)
                if count > MAX_CELLS:
                    raise ValueError("原表快照超过单次处理上限")
                rows.append(row)
            dates: dict[date, int] = {}
            ambiguous: set[date] = set()
            dated = item.get("row_dates", [])
            if not isinstance(dated, list):
                raise ValueError("原表缺少日期索引")
            for entry in dated:
                if not isinstance(entry, dict):
                    raise ValueError("原表日期索引无效")
                raw_day, row_index = entry.get("date"), entry.get("row")
                if (
                    not isinstance(raw_day, str)
                    or type(row_index) is not int
                    or not 1 <= row_index <= len(rows)
                ):
                    raise ValueError("原表日期索引超出范围")
                day = date.fromisoformat(raw_day)
                if day in dates or day in ambiguous:
                    if period is None or (day.year, day.month) == period:
                        raise ValueError("原表存在重复日期，不能任意选择日期行")
                    dates.pop(day, None)
                    ambiguous.add(day)
                    continue
                dates[day] = row_index
            sheets[name] = SourceSheet([str(x) for x in headers], rows, dates)
        workbook = cls(sheets, source_period(payload))
        workbook.field_mappings = build_field_mappings(payload)
        return workbook

    def business_cell(
        self, definition: MeterDefinition | RuleDefinition, day: date
    ) -> WorkbookCell:
        field = self.field_for(definition)
        if field is None:
            return WorkbookCell(
                status="source_field_missing",
                provenance={
                    "business_key": definition_key(definition),
                    "business_name": definition_label(definition),
                    "source_sheet": self.resolve_sheet(definition.source_sheet),
                    "canonical_source_column": definition.source_column,
                },
            )
        column = field.get("source_column")
        if not isinstance(column, int):
            raise ValueError("原表字段映射缺少列号")
        cell = self.cell_on(str(field["source_sheet"]), column, day)
        cell.provenance.update(
            business_key=field["business_key"],
            business_sheet=field["business_sheet"],
            business_name=field["business_name"],
            source_column=column,
            canonical_source_column=definition.source_column,
        )
        return cell

    def field_for(
        self, definition: MeterDefinition | RuleDefinition
    ) -> dict[str, JsonValue] | None:
        key = definition.source_sheet, definition.name, definition.source_column
        if key not in self._field_bindings:
            self._field_bindings[key] = find_field(self.field_mappings, definition)
        return self._field_bindings[key]

    def reference_on(
        self, definition: MeterDefinition | RuleDefinition, day: date
    ) -> dict[str, JsonValue]:
        """Archive evidence only; never evaluate or apply a reported result."""
        field = self.field_for(definition)
        if field is None:
            return {}
        sheet = str(field["source_sheet"])
        source = self.sheets[sheet]
        row = source.dates.get(day)
        if row is None:
            return {}
        address = f"{get_column_letter(int(str(field['source_column'])))}{row}"
        raw = self._raw(sheet, address)
        return {
            "source_sheet": sheet,
            "source_cell": address,
            "date": day.isoformat(),
            "formula": raw if isinstance(raw, str) and raw.startswith("=") else None,
            "reported_value": str(raw)
            if raw is not None and not (isinstance(raw, str) and raw.startswith("="))
            else None,
            "business_key": field["business_key"],
            "business_name": field["business_name"],
            "source_column": field["source_column"],
        }

    def resolve_sheet(self, name: str) -> str:
        if name in self.sheets:
            return name
        return next(
            (
                item
                for item in self.sheets
                if canonical_sheet(item) == canonical_sheet(name)
            ),
            name,
        )

    def covers(self, year: int, month: int) -> bool:
        if self.period is not None:
            return self.period == (year, month)
        return any(
            day.year == year and day.month == month
            for sheet in self.sheets.values()
            for day in sheet.dates
        )

    def set_reading(
        self, sheet: str, column: int, day: date, value: Decimal, *, version: int
    ) -> None:
        sheet = self.resolve_sheet(sheet)
        source = self.sheets.get(sheet)
        if source is None:
            return
        if day not in source.dates:
            ordered = sorted(source.dates.items(), key=lambda item: item[1])
            if len(ordered) < 2 or day != ordered[-1][0] + timedelta(days=1):
                return
            (before_day, before_row), (last_day, last_row) = ordered[-2:]
            if last_day - before_day != timedelta(days=1) or last_row != before_row + 1:
                return
            row: list[JsonValue] = [day.isoformat()]
            template = source.grid[last_row - 1]
            for index, original in enumerate(template[1:], 2):
                row.append(
                    Translator(
                        original, origin=f"{get_column_letter(index)}{last_row}"
                    ).translate_formula(f"{get_column_letter(index)}{last_row + 1}")
                    if isinstance(original, str) and original.startswith("=")
                    else None
                )
            while len(source.grid) < last_row:
                source.grid.append([])
            if len(source.grid) > last_row:
                if any(value is not None for value in source.grid[last_row]):
                    raise ValueError("次日模板行存在未标注日期的数据，请先核对")
                source.grid[last_row] = row
            else:
                source.grid.append(row)
            source.dates[day] = last_row + 1
        address = f"{get_column_letter(column)}{source.dates[day]}"
        original = self._raw(sheet, address)
        if isinstance(original, str) and original.startswith("="):
            raise ValueError("原表公式列不能被人工读数覆盖")
        if not value.is_finite() or abs(value) >= Decimal("1e20"):
            raise ValueError("原始读数超出计量范围")
        self._readings[sheet, address] = value, version
        self._cache.clear()
        self._values.clear()

    def require_inputs(self, fields: set[tuple[str, int]]) -> None:
        self._required_inputs = fields
        self._cache.clear()
        self._values.clear()

    def cell_on(self, sheet: str, column: int, day: date) -> WorkbookCell:
        sheet = self.resolve_sheet(sheet)
        source = self.sheets.get(sheet)
        if source is None or day not in source.dates:
            return WorkbookCell(status="not_applicable")
        return self.result(sheet, f"{get_column_letter(column)}{source.dates[day]}")

    def set_reviews(self, reviews: list[UsageReview]) -> None:
        self._reviews.clear()
        for review in reviews:
            name = self.resolve_sheet(review.dataset)
            source = self.sheets.get(name)
            if source is None:
                continue
            for day, row in source.dates.items():
                evidence = review.evidence_on(day)
                if evidence:
                    key = name, f"{get_column_letter(review.column)}{row}"
                    self._reviews.setdefault(key, []).extend(evidence)
        self._cache.clear()
        self._values.clear()

    def _raw(self, sheet: str, address: str) -> JsonValue:
        source = self.sheets.get(sheet)
        if source is None:
            raise SourceFormulaError("source_missing_sheet")
        match = ADDRESS.fullmatch(address)
        if match is None:
            raise SourceFormulaError("source_formula_error")
        row, column = int(match[2]), column_index_from_string(match[1])
        if row > 5000 or column > 200:
            raise SourceFormulaError("source_formula_error")
        # A known worksheet's empty cells have Excel blank-reference semantics.
        if row > len(source.grid) or column > len(source.grid[row - 1]):
            return None
        return source.grid[row - 1][column - 1]

    @staticmethod
    def _number(value: JsonValue) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise SourceFormulaError("source_non_numeric")
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise SourceFormulaError("source_non_numeric") from exc
        if not result.is_finite() or abs(result) >= Decimal("1e20"):
            raise SourceFormulaError("out_of_range")
        return result

    def result(
        self, sheet: str, address: str, stack: tuple[tuple[str, str], ...] = ()
    ) -> WorkbookCell:
        key = sheet, address
        if key in stack or len(stack) >= 64:
            return WorkbookCell(status="source_formula_cycle")
        if key in self._cache:
            return self._cache[key].model_copy(deep=True)
        provenance: dict[str, JsonValue] = {
            "source_kind": "literal",
            "source_sheet": sheet,
            "source_cell": address,
        }
        try:
            raw = self._raw(sheet, address)
            if key in self._readings:
                value, version = self._readings[key]
                provenance.update(source_kind="reading", version=version)
            elif isinstance(raw, str) and raw.startswith("="):
                provenance.update(source_kind="formula", formula=raw)
                value, sources = self._formula(sheet, raw, stack + (key,))
                provenance["sources"] = sources
            elif raw is None or raw == "":
                parts = ADDRESS.fullmatch(address)
                if (
                    parts
                    and (sheet, column_index_from_string(parts[1]))
                    in self._required_inputs
                ):
                    raise SourceFormulaError("missing_reading")
                return WorkbookCell(status="source_blank", provenance=provenance)
            else:
                value = self._number(raw)
            if not value.is_finite() or abs(value) >= Decimal("1e20"):
                raise SourceFormulaError("out_of_range")
            with localcontext() as context:
                context.prec = 60
                self._values[key] = value
                display_value = value.quantize(Decimal(".00000001"))
            reviews: list[JsonValue] = list(self._reviews.get(key, []))
            dependencies = provenance.get("sources", [])
            if isinstance(dependencies, list):
                for source in dependencies:
                    pending = source.get("review") if isinstance(source, dict) else None
                    if isinstance(pending, list):
                        reviews.extend(item for item in pending if item not in reviews)
            if reviews:
                provenance["review"] = reviews
            cell = WorkbookCell(
                value=display_value,
                calculated_value=display_value,
                status="pending_review" if reviews else "complete",
                provenance=provenance,
            )
        except SourceFormulaError as exc:
            parts = ADDRESS.fullmatch(address)
            required = bool(
                parts
                and (sheet, column_index_from_string(parts[1])) in self._required_inputs
            )
            if required and exc.status == "source_non_numeric":
                provenance["reason"] = "必需填报字段不是有效数字"
                cell = WorkbookCell(status="pending_review", provenance=provenance)
            else:
                cell = WorkbookCell(status=exc.status, provenance=provenance)
        except (ArithmeticError, SyntaxError, RecursionError):
            cell = WorkbookCell(status="source_formula_error", provenance=provenance)
        self._cache[key] = cell
        return cell.model_copy(deep=True)

    def _formula(
        self, sheet: str, formula: str, stack: tuple[tuple[str, str], ...]
    ) -> tuple[Decimal, list[JsonValue]]:
        if len(formula) > 2048:
            raise SourceFormulaError("source_formula_error")
        references: dict[str, tuple[str, str]] = {}
        evidence: list[JsonValue] = []
        body = formula[1:]

        def replace(match: re.Match[str]) -> str:
            source = match["sheet"] or sheet
            if (
                not match["sheet"]
                and body[: match.start()].rstrip().endswith(":")
                and references
            ):
                source = references[f"cell_{len(references) - 1}"][0]
            if source.startswith("'"):
                source = source[1:-1].replace("''", "'")
            token = f"cell_{len(references)}"
            references[token] = source, match["column"] + match["row"]
            return token

        expression = REFERENCE.sub(replace, body)
        scalar_range = re.fullmatch(r"@?(cell_\d+):(cell_\d+)", expression.strip())
        if scalar_range:
            # Legacy scalar formulas use Excel's implicit intersection: take
            # the range cell on the formula's own row or column, never its sum.
            left, right = references[scalar_range[1]], references[scalar_range[2]]
            a, b = ADDRESS.fullmatch(left[1]), ADDRESS.fullmatch(right[1])
            current = ADDRESS.fullmatch(stack[-1][1]) if stack else None
            if left[0] != right[0] or a is None or b is None or current is None:
                raise SourceFormulaError("source_formula_error")
            if a.groups() == b.groups():
                address = left[1]
            elif a[1] == b[1] and int(a[2]) <= int(current[2]) <= int(b[2]):
                address = a[1] + current[2]
            elif a[2] == b[2] and (
                column_index_from_string(a[1])
                <= column_index_from_string(current[1])
                <= column_index_from_string(b[1])
            ):
                address = current[1] + a[2]
            else:
                raise SourceFormulaError("source_formula_error")
            references["cell_intersection"] = left[0], address
            expression = "cell_intersection"

        def expand(match: re.Match[str]) -> str:
            left, right = references[match[1]], references[match[2]]
            a, b = ADDRESS.fullmatch(left[1]), ADDRESS.fullmatch(right[1])
            if left[0] != right[0] or a is None or b is None:
                raise SourceFormulaError("source_formula_error")
            tokens: list[str] = []
            for row in range(int(a[2]), int(b[2]) + 1):
                for column in range(
                    column_index_from_string(a[1]), column_index_from_string(b[1]) + 1
                ):
                    if len(references) >= 1000:
                        raise SourceFormulaError("source_formula_error")
                    token = f"cell_{len(references)}"
                    references[token] = left[0], f"{get_column_letter(column)}{row}"
                    tokens.append(token)
            return ",".join(tokens)

        expression = re.sub(r"(cell_\d+):(cell_\d+)", expand, expression)
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 2000:
            raise SourceFormulaError("source_formula_error")

        def run(node: ast.AST, *, in_sum: bool = False) -> Decimal:
            if isinstance(node, ast.Expression):
                return run(node.body)
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return self._number(str(node.value))
            if isinstance(node, ast.Name) and node.id in references:
                source, address = references[node.id]
                cell = self.result(source, address, stack)
                evidence.append(
                    {
                        "sheet": source,
                        "cell": address,
                        "value": str(cell.value) if cell.value is not None else None,
                        "status": cell.status,
                        "review": cell.provenance.get("review", []),
                    }
                )
                if cell.status == "source_blank" or (
                    in_sum and cell.status == "source_non_numeric"
                ):
                    return Decimal(0)
                if cell.value is None:
                    raise SourceFormulaError(cell.status)
                # Excel keeps intermediate precision. Only presentation/storage
                # rounds to eight places, never a dependency feeding a formula.
                return self._values.get((source, address), cell.value)
            if isinstance(node, ast.UnaryOp) and isinstance(
                node.op, (ast.USub, ast.UAdd)
            ):
                value = run(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            if isinstance(node, ast.BinOp):
                left, right = run(node.left), run(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    if not right:
                        raise SourceFormulaError("zero_denominator")
                    return left / right
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id.upper() == "SUM"
                and not node.keywords
            ):
                return sum((run(arg, in_sum=True) for arg in node.args), Decimal(0))
            raise SourceFormulaError("source_formula_error")

        with localcontext() as context:
            context.prec = 60
            return run(tree), evidence
