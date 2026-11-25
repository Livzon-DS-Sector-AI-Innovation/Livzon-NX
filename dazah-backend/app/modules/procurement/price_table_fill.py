"""Fill missing unit prices in an uploaded spreadsheet.

表格不预设模板：先按表头关键词和数据特征自动识别「编码 / 名称 / 单价」列，
调用方可以回传 mapping 覆盖自动识别结果。回填只改目标列的值，其余单元格、
样式、合并单元格保持原样，并追加一个「匹配说明」工作表。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.price_live_source import list_live_prices
from app.modules.procurement.repository import MaterialPriceRepository

CODE_HEADER_PATTERN = re.compile(r"(物料)?(编码|编号|代码|料号)")
NAME_HEADER_PATTERN = re.compile(r"(物料)?(名称|说明|描述|品名|物品)")
PRICE_HEADER_PATTERN = re.compile(r"单价|价格")
QUANTITY_HEADER_PATTERN = re.compile(r"数量")
AMOUNT_HEADER_PATTERN = re.compile(r"金额|总价|合计")
CODE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_\.]{3,31}$")
HEADER_SCAN_ROWS = 15
PREVIEW_ROW_LIMIT = 200
NAME_MATCH_THRESHOLD = 0.6
MAX_NAME_LOOKUPS = 300

MATCH_SOURCE_LABELS = {
    "live": "仓储实时入库",
    "history": "历史采购价",
    "name_fuzzy": "名称模糊匹配",
    "unmatched": "未匹配",
}


@dataclass(frozen=True)
class ColumnMapping:
    sheet_name: str
    header_row: int
    code_column: int | None
    name_column: int | None
    price_column: int | None
    quantity_column: int | None = None
    amount_column: int | None = None

    @property
    def fillable(self) -> bool:
        return self.price_column is not None and (
            self.code_column is not None or self.name_column is not None
        )


@dataclass
class FillMatch:
    row_number: int
    material_code: str
    material_name: str
    matched_code: str | None
    matched_name: str | None
    unit: str
    unit_price: Decimal | None
    source: str
    message: str


def _cell_text(worksheet: Worksheet, row: int, column: int | None) -> str:
    if column is None:
        return ""
    value = worksheet.cell(row=row, column=column).value
    if value is None:
        return ""
    return str(value).strip()


def _row_is_empty(worksheet: Worksheet, row: int, max_column: int) -> bool:
    return all(
        worksheet.cell(row=row, column=column).value in (None, "")
        for column in range(1, max_column + 1)
    )


def _header_score(values: list[object]) -> int:
    text = " ".join(str(value) for value in values if value not in (None, ""))
    score = 0
    if CODE_HEADER_PATTERN.search(text):
        score += 3
    if NAME_HEADER_PATTERN.search(text):
        score += 2
    if PRICE_HEADER_PATTERN.search(text):
        score += 3
    if QUANTITY_HEADER_PATTERN.search(text) or AMOUNT_HEADER_PATTERN.search(text):
        score += 1
    return score


def _find_header_row(worksheet: Worksheet, max_column: int) -> int:
    best_row = 1
    best_key = (-1, -1)
    for row in range(1, min(HEADER_SCAN_ROWS, worksheet.max_row) + 1):
        values = [
            worksheet.cell(row=row, column=column).value
            for column in range(1, max_column + 1)
        ]
        non_empty = sum(1 for value in values if value not in (None, ""))
        key = (_header_score(values), non_empty)
        if key > best_key:
            best_key = key
            best_row = row
    return best_row


def _detect_code_column(
    worksheet: Worksheet,
    header_row: int,
    max_column: int,
    excluded: set[int],
) -> int | None:
    for column in range(1, max_column + 1):
        title = _cell_text(worksheet, header_row, column)
        if CODE_HEADER_PATTERN.search(title):
            return column
    # 表头认不出时按数据特征兜底：绝大多数单元格像编码。
    best: tuple[float, int] | None = None
    sample_rows = range(header_row + 1, min(header_row + 50, worksheet.max_row) + 1)
    for column in range(1, max_column + 1):
        if column in excluded:
            continue
        values = [
            _cell_text(worksheet, row, column)
            for row in sample_rows
            if _cell_text(worksheet, row, column)
        ]
        if len(values) < 3:
            continue
        ratio = sum(1 for value in values if CODE_VALUE_PATTERN.match(value)) / len(
            values
        )
        if ratio >= 0.6 and (best is None or ratio > best[0]):
            best = (ratio, column)
    return best[1] if best else None


def _detect_name_column(
    worksheet: Worksheet,
    header_row: int,
    max_column: int,
    excluded: set[int],
) -> int | None:
    for column in range(1, max_column + 1):
        if column in excluded:
            continue
        title = _cell_text(worksheet, header_row, column)
        if NAME_HEADER_PATTERN.search(title):
            return column
    # 兜底：剩余列中文本最长的一列。
    best: tuple[int, int] | None = None
    sample_rows = range(header_row + 1, min(header_row + 50, worksheet.max_row) + 1)
    for column in range(1, max_column + 1):
        if column in excluded:
            continue
        lengths = [
            len(_cell_text(worksheet, row, column))
            for row in sample_rows
            if _cell_text(worksheet, row, column)
        ]
        if len(lengths) < 3:
            continue
        longest = max(lengths)
        if longest >= 4 and (best is None or longest > best[0]):
            best = (longest, column)
    return best[1] if best else None


def detect_columns(worksheet: Worksheet) -> ColumnMapping:
    max_column = max(worksheet.max_column or 1, 1)
    header_row = _find_header_row(worksheet, max_column)

    code_column = None
    name_column = None
    price_column = None
    quantity_column = None
    amount_column = None
    for column in range(1, max_column + 1):
        title = _cell_text(worksheet, header_row, column)
        if not title:
            continue
        if price_column is None and PRICE_HEADER_PATTERN.search(title):
            price_column = column
        elif quantity_column is None and QUANTITY_HEADER_PATTERN.search(title):
            quantity_column = column
        elif amount_column is None and AMOUNT_HEADER_PATTERN.search(title):
            amount_column = column
        elif code_column is None and CODE_HEADER_PATTERN.search(title):
            code_column = column
        elif name_column is None and NAME_HEADER_PATTERN.search(title):
            name_column = column

    excluded = {
        column
        for column in (price_column, quantity_column, amount_column)
        if column is not None
    }
    if code_column is None:
        code_column = _detect_code_column(worksheet, header_row, max_column, excluded)
    if name_column is None:
        if code_column:
            excluded.add(code_column)
        name_column = _detect_name_column(
            worksheet, header_row, max_column, excluded
        )

    return ColumnMapping(
        sheet_name=worksheet.title,
        header_row=header_row,
        code_column=code_column,
        name_column=name_column,
        price_column=price_column,
        quantity_column=quantity_column,
        amount_column=amount_column,
    )


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("¥", "").replace("￥", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s,，。;；:：*/\-—_（）()]+", "", value).lower()


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_name(left), _normalize_name(right)).ratio()


async def _load_price_context(
    db: AsyncSession,
    codes: list[str],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    repository = MaterialPriceRepository(db)
    history = await repository.latest_price_by_codes(codes)
    live_records = await list_live_prices(db, material_codes=set(codes))
    latest_live: dict[str, dict[str, object]] = {}
    for record in live_records:
        current = latest_live.get(record.material_code)
        if current is None or (record.data_date or "") > (
            current.get("data_date") or ""
        ):
            latest_live[record.material_code] = {
                "unit_price": record.unit_price,
                "unit": record.unit,
                "material_name": record.material_name,
                "data_date": record.data_date,
            }
    return history, latest_live


def _pick_price(
    code: str,
    history: dict[str, dict[str, object]],
    live: dict[str, dict[str, object]],
) -> tuple[Decimal | None, str, str, str]:
    """返回 (单价, 来源, 匹配编码, 单位)。实时数据优先。"""
    live_hit = live.get(code)
    history_hit = history.get(code)
    if live_hit is not None:
        return (
            live_hit["unit_price"],  # type: ignore[return-value]
            "live",
            code,
            str(live_hit.get("unit") or ""),
        )
    if history_hit is not None:
        return (
            history_hit["avg_price"],  # type: ignore[return-value]
            "history",
            code,
            str(history_hit.get("unit") or ""),
        )
    return None, "unmatched", "", ""


async def _match_by_name(
    db: AsyncSession,
    name: str,
) -> tuple[str | None, str | None, Decimal | None, str]:
    if not name.strip():
        return None, None, None, ""
    candidates = await MaterialPriceRepository(db).search_by_name(name)
    if not candidates:
        return None, None, None, ""
    scored = sorted(
        candidates,
        key=lambda item: _similarity(name, item[1]),
        reverse=True,
    )
    best = scored[0]
    score = _similarity(name, best[1])
    if score < NAME_MATCH_THRESHOLD:
        return None, None, None, ""
    return best[0], best[1], best[3], best[2]


async def preview_fill(
    db: AsyncSession,
    file_bytes: bytes,
    *,
    mapping: ColumnMapping | None = None,
) -> tuple[ColumnMapping, list[str], list[FillMatch], int]:
    workbook = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=False)
    try:
        worksheet = (
            workbook[mapping.sheet_name]
            if mapping is not None and mapping.sheet_name in workbook.sheetnames
            else workbook.active
        )
        resolved = mapping or detect_columns(worksheet)
        max_column = max(worksheet.max_column or 1, 1)
        rows: list[tuple[int, str, str]] = []
        for row in range(resolved.header_row + 1, worksheet.max_row + 1):
            if _row_is_empty(worksheet, row, max_column):
                continue
            code = _cell_text(worksheet, row, resolved.code_column)
            name = _cell_text(worksheet, row, resolved.name_column)
            if not code and not name:
                continue
            rows.append((row, code, name))

        codes = [code for _, code, _ in rows if code]
        history, live = await _load_price_context(db, codes)
        matches: list[FillMatch] = []
        name_lookup_budget = MAX_NAME_LOOKUPS
        for row, code, name in rows:
            price: Decimal | None = None
            source = "unmatched"
            matched_code: str | None = None
            matched_name: str | None = None
            unit = ""
            message_text = MATCH_SOURCE_LABELS["unmatched"]
            if code:
                price, source, matched_code, unit = _pick_price(code, history, live)
                if price is None:
                    matched_code = None
            if price is None and name:
                if name_lookup_budget > 0:
                    name_lookup_budget -= 1
                    fuzzy_code, fuzzy_name, fuzzy_price, fuzzy_unit = (
                        await _match_by_name(db, name)
                    )
                    if fuzzy_price is not None:
                        price = fuzzy_price
                        source = "name_fuzzy"
                        matched_code = fuzzy_code
                        matched_name = fuzzy_name
                        unit = fuzzy_unit
                else:
                    message_text = "名称匹配次数超限，请补充物料编码后重试"
            if price is not None and matched_code:
                hint = history.get(matched_code) or live.get(matched_code) or {}
                matched_name = str(hint.get("material_name") or matched_name or "")
            if source == "unmatched":
                final_message = message_text
            else:
                final_message = MATCH_SOURCE_LABELS.get(source, source)
            matches.append(
                FillMatch(
                    row_number=row,
                    material_code=code,
                    material_name=name,
                    matched_code=matched_code,
                    matched_name=matched_name,
                    unit=unit,
                    unit_price=price,
                    source=source,
                    message=final_message,
                )
            )
        headers = [
            _cell_text(worksheet, resolved.header_row, column)
            for column in range(1, max_column + 1)
        ]
        return resolved, headers, matches, len(rows)
    finally:
        workbook.close()


def fill_workbook(
    file_bytes: bytes,
    *,
    mapping: ColumnMapping,
    matches: list[FillMatch],
    only_blank: bool = True,
) -> tuple[bytes, int]:
    """把匹配结果写入副本，返回 (文件字节, 实际写入单元格数)。"""
    workbook = load_workbook(io.BytesIO(file_bytes), keep_vba=True)
    try:
        worksheet = (
            workbook[mapping.sheet_name]
            if mapping.sheet_name in workbook.sheetnames
            else workbook.active
        )
        price_column = mapping.price_column
        if price_column is None:
            raise ValueError("未识别到单价列，无法回填")
        written = 0
        for match in matches:
            if match.unit_price is None:
                continue
            cell = worksheet.cell(row=match.row_number, column=price_column)
            if only_blank and cell.value not in (None, ""):
                continue
            cell.value = float(match.unit_price)
            cell.number_format = "0.00"
            written += 1

        note = workbook.create_sheet("匹配说明")
        note.append(
            [
                "行号",
                "原物料编码",
                "原物料名称",
                "匹配物料编码",
                "匹配物料名称",
                "单价",
                "来源",
                "说明",
            ]
        )
        for match in matches:
            note.append(
                [
                    match.row_number,
                    match.material_code,
                    match.material_name,
                    match.matched_code or "",
                    match.matched_name or "",
                    float(match.unit_price) if match.unit_price is not None else "",
                    MATCH_SOURCE_LABELS.get(match.source, match.source),
                    match.message,
                ]
            )
        note.column_dimensions[get_column_letter(1)].width = 8
        note.column_dimensions[get_column_letter(3)].width = 36
        note.column_dimensions[get_column_letter(5)].width = 36

        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue(), written
    finally:
        workbook.close()
