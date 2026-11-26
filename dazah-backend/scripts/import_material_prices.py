"""按列映射导入历史物料采购价格。

支持 .xls（xlrd）与 .xlsx（openpyxl）。映射 JSON 声明列名、年度来源和幂等指纹，
新增表格只需新增一份映射，不改代码。

用法（在 dazah-backend 容器内，PYTHONPATH=/app）：

    python /tmp/import_material_prices.py \
        --mapping /tmp/price_mappings/cux_stock.json \
        --files /tmp/cux1.xls ... --dry-run

    # 正式导入；导入完成后会自动标记同物料价格离散 >3 倍的行
    python /tmp/import_material_prices.py --mapping ... --dir /tmp/data
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import xlrd
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session_factory
from app.modules.procurement.models import MaterialPriceRecord

DATE_SERIAL_MIN = 30000
DATE_SERIAL_MAX = 60000
WRITE_BATCH_SIZE = 500

ANOMALY_SQL = text(
    """
    WITH stats AS (
        SELECT material_code,
               MIN(unit_price) AS min_price,
               MAX(unit_price) AS max_price,
               COUNT(*) AS batch_count
        FROM procurement.material_price_records
        WHERE is_deleted = false AND unit_price > 0
        GROUP BY material_code
    )
    UPDATE procurement.material_price_records AS r
    SET price_flag = CASE
            WHEN s.batch_count >= 3
                 AND s.max_price > s.min_price * 3
            THEN 'suspicious'
            ELSE 'normal'
        END
    FROM stats AS s
    WHERE r.material_code = s.material_code
      AND r.is_deleted = false
      AND r.price_flag IS DISTINCT FROM CASE
            WHEN s.batch_count >= 3
                 AND s.max_price > s.min_price * 3
            THEN 'suspicious'
            ELSE 'normal'
        END
    """
)


def normalize_material_code(value: Any) -> str:
    text_value = str(value).strip()
    if not text_value:
        return ""
    try:
        number = float(text_value)
    except ValueError:
        return text_value
    return str(int(number)) if number == int(number) else text_value


def to_decimal(value: Any) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (ArithmeticError, ValueError):
        return Decimal("0")


def cell_text(rows: list[list[Any]], row: int, column: int) -> str:
    if row >= len(rows) or column < 0 or column >= len(rows[row]):
        return ""
    return str(rows[row][column]).strip()


def cell_number(rows: list[list[Any]], row: int, column: int) -> Decimal:
    if row >= len(rows) or column < 0 or column >= len(rows[row]):
        return Decimal("0")
    return to_decimal(rows[row][column])


def read_sheets(path: Path) -> list[tuple[str, list[list[Any]], int]]:
    """返回 [(sheet_name, rows, datemode)]。datemode 供 Excel 日期序列号解析。"""
    if path.suffix.lower() == ".xls":
        workbook = xlrd.open_workbook(str(path), on_demand=True)
        try:
            sheets: list[tuple[str, list[list[Any]], int]] = []
            for name in workbook.sheet_names():
                sheet = workbook.sheet_by_name(name)
                rows = [
                    [sheet.cell_value(row, column) for column in range(sheet.ncols)]
                    for row in range(sheet.nrows)
                ]
                sheets.append((name, rows, workbook.datemode))
            return sheets
        finally:
            workbook.release_resources()

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    try:
        sheets: list[tuple[str, list[list[Any]], int]] = []
        for worksheet in workbook.worksheets:
            sheets.append(
                (
                    worksheet.title,
                    [list(row) for row in worksheet.iter_rows(values_only=True)],
                    0,
                )
            )
        return sheets
    finally:
        workbook.close()


def find_header(
    rows: list[list[Any]], markers: list[str]
) -> tuple[int, dict[str, int]] | None:
    for row_index in range(min(30, len(rows))):
        values = [str(value).strip() for value in rows[row_index]]
        if all(marker in values for marker in markers):
            return row_index, {name: i for i, name in enumerate(values) if name}
    return None


def detect_year(
    rows: list[list[Any]], header_row: int, datemode: int
) -> int | None:
    for row_index in range(header_row):
        for value in rows[row_index]:
            if isinstance(value, datetime):
                return value.year
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if not DATE_SERIAL_MIN < float(value) < DATE_SERIAL_MAX:
                continue
            try:
                parts = xlrd.xldate_as_tuple(float(value), datemode)
            except (ValueError, OverflowError):
                continue
            if parts[0] >= 1900:
                return int(parts[0])
    return None


def build_row(
    rows: list[list[Any]],
    row_index: int,
    index: dict[str, int],
    *,
    mapping: dict[str, Any],
    year: int,
    source_file: str,
    source_sheet: str,
) -> dict[str, Any] | None:
    columns: dict[str, str] = mapping["columns"]
    code = normalize_material_code(
        rows[row_index][index[columns["material_code"]]]
        if columns["material_code"] in index
        else ""
    )
    if not code:
        return None

    def text_field(field: str) -> str:
        header = columns.get(field)
        if not header or header not in index:
            return ""
        return cell_text(rows, row_index, index[header])

    def number_field(field: str) -> Decimal:
        header = columns.get(field)
        if not header or header not in index:
            return Decimal("0")
        return cell_number(rows, row_index, index[header])

    unit_price = number_field("unit_price")
    received = number_field("received_quantity")
    returned = number_field("returned_quantity")
    quantity = received + returned
    amount = quantity * unit_price

    record: dict[str, Any] = {
        "id": uuid4(),
        "data_year": year,
        "data_date": None,
        "doc_no": text_field("doc_no"),
        "department": text_field("department"),
        "sub_inventory": text_field("sub_inventory"),
        "batch_no": text_field("batch_no"),
        "material_code": code,
        "material_name": text_field("material_name"),
        "material_alias": text_field("material_alias"),
        "unit": text_field("unit"),
        "material_category": text_field("material_category"),
        "cost_category": text_field("cost_category"),
        "unit_price": unit_price,
        "quantity": quantity,
        "amount": amount,
        "supplier_name": text_field("supplier_name"),
        "price_flag": "normal",
        "source_type": mapping["source_type"],
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": row_index + 1,
        "raw_data": {
            name: (
                str(rows[row_index][column])
                if column < len(rows[row_index]) and rows[row_index][column] is not None
                else ""
            )
            for name, column in index.items()
        },
        "is_deleted": False,
    }
    key_parts = [
        str(record[field]) if record.get(field) is not None else ""
        for field in mapping["row_key_fields"]
    ]
    record["row_key"] = hashlib.sha256(
        "|".join(key_parts).encode("utf-8")
    ).hexdigest()[:96]
    return record


def collect_records(
    paths: list[Path], mapping: dict[str, Any], fallback_year: int | None
) -> tuple[list[dict[str, Any]], Counter[str]]:
    records: list[dict[str, Any]] = []
    report: Counter[str] = Counter()
    markers: list[str] = mapping["header_markers"]
    for path in paths:
        for sheet_name, rows, datemode in read_sheets(path):
            if not rows:
                continue
            header = find_header(rows, markers)
            if header is None:
                report[f"{path.name}/{sheet_name}: 跳过（未找到表头）"] += 1
                continue
            header_row, index = header
            year = detect_year(rows, header_row, datemode) or fallback_year
            if year is None:
                report[f"{path.name}/{sheet_name}: 跳过（无法识别年度）"] += 1
                continue
            count = 0
            for row_index in range(header_row + 1, len(rows)):
                record = build_row(
                    rows,
                    row_index,
                    index,
                    mapping=mapping,
                    year=year,
                    source_file=path.name,
                    source_sheet=sheet_name,
                )
                if record is not None:
                    records.append(record)
                    count += 1
            report[f"{path.name}/{sheet_name}: {year} 年 {count} 行"] += 1
    return records, report


async def write_records(records: list[dict[str, Any]]) -> int:
    """分批写库：每批一条多值 INSERT，并在批内提交，避免长事务。

    注意：``pg_insert(table).values(batch)`` 已经带上数据，不能把 batch 再作为
    execute 的第二参数传入，否则 SQLAlchemy 会退化成逐行 executemany。
    """
    table = MaterialPriceRecord.__table__
    written = 0
    async with async_session_factory() as session:
        for start in range(0, len(records), WRITE_BATCH_SIZE):
            batch = records[start : start + WRITE_BATCH_SIZE]
            statement = pg_insert(table).values(batch)
            statement = statement.on_conflict_do_update(
                index_elements=[table.c.row_key],
                set_={
                    column: statement.excluded[column]
                    for column in (
                        "data_date",
                        "doc_no",
                        "department",
                        "sub_inventory",
                        "batch_no",
                        "material_name",
                        "material_alias",
                        "unit",
                        "material_category",
                        "cost_category",
                        "unit_price",
                        "quantity",
                        "amount",
                        "supplier_name",
                        "source_file",
                        "source_sheet",
                        "source_row",
                        "raw_data",
                        "is_deleted",
                    )
                },
            )
            await session.execute(statement)
            written += len(batch)
            await session.commit()
        await session.execute(ANOMALY_SQL)
        await session.commit()
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按列映射导入历史物料采购价格")
    parser.add_argument("--mapping", type=Path, required=True, help="映射 JSON")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", type=Path, help="报表目录")
    source.add_argument("--files", type=Path, nargs="+", help="报表文件")
    parser.add_argument("--year", type=int, default=None, help="无法识别年度时的兜底")
    parser.add_argument("--dry-run", action="store_true", help="只解析统计，不写库")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    paths = sorted(args.dir.glob("*")) if args.dir else list(args.files)
    paths = [p for p in paths if p.suffix.lower() in {".xls", ".xlsx"}]
    if not paths:
        print("没有找到 .xls/.xlsx 文件", file=sys.stderr)
        return 2

    records, report = collect_records(paths, mapping, args.year)
    for line in sorted(report):
        print(f"  {line}")
    years = Counter(record["data_year"] for record in records)
    total_amount = sum(record["amount"] for record in records)
    print(f"\n解析 {len(records)} 行，金额合计 {total_amount:,.2f}")
    print(f"年度分布：{dict(sorted(years.items(), key=lambda kv: str(kv[0])))}")
    if args.dry_run:
        print("dry-run：未写入数据库")
        return 0

    written = await write_records(records)
    print(f"已写入/更新 {written} 行，并完成价格异常标记")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
