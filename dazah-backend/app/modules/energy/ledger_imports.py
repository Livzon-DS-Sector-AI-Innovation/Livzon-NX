"""Bounded XLSX preview; source literals are imported only after explicit mapping."""

import hashlib
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import openpyxl
from openpyxl.utils.datetime import from_excel
from pydantic import JsonValue
from sqlalchemy import select

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import (
    EnergyImportBatch,
    EnergyMeterPoint,
    EnergyReading,
)
from app.modules.energy.ledger_schemas import (
    DirectReadingValue,
    DirectReadingWrite,
    ImportConfirm,
    ImportResponse,
    MeterDefinition,
)
from app.modules.energy.ledger_service import EnergyLedgerService

if TYPE_CHECKING:
    from app.modules.energy.ledger_template import TemplateDraftResponse
from app.modules.energy.ledger_source_policy import (
    SOURCE_CATEGORIES as SOURCE_CATEGORIES,
)
from app.modules.energy.ledger_source_policy import (
    calculated_columns as calculated_columns,
)
from app.modules.energy.ledger_source_policy import (
    input_column_allowed as input_column_allowed,
)

IMPORT_POLICY_VERSION = 3


def validate_import_period(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise AppException(422, "有效结束日期不能早于开始日期")


def in_import_period(day: date, start: date | None, end: date | None) -> bool:
    return (start is None or day >= start) and (end is None or day <= end)


def parse_source_date(value: object, year: int) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"(?:(\d{4})[-/])?(\d{1,2})[-/](\d{1,2})", value.strip())
        if match:
            try:
                return date(int(match[1] or year), int(match[2]), int(match[3]))
            except ValueError:
                return None
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 20000 <= value <= 100000
    ):
        converted = from_excel(value)
        return converted.date() if isinstance(converted, datetime) else None
    return None


def inspect_xlsx(
    content: bytes,
    year: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, JsonValue]:
    validate_import_period(start_date, end_date)
    if not 2000 <= year <= 2100:
        raise AppException(422, "导入年份须在 2000 至 2100 年之间")
    if len(content) > 10 * 1024 * 1024:
        raise AppException(413, "Excel 文件不能超过 10 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if (
                sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024
                or len(archive.infolist()) > 2000
            ):
                raise AppException(413, "Excel 解压内容超过允许上限")
        workbook = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=False, keep_links=False
        )
    except (zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
        raise AppException(422, "文件不是有效的 XLSX 工作簿") from exc
    sheets: list[JsonValue] = []
    warnings: list[JsonValue] = []
    formulas: list[JsonValue] = []
    source_cell_count = 0
    try:
        for sheet in workbook:
            sheet.reset_dimensions()
            source_grid: list[JsonValue] = []
            cells: list[JsonValue] = []
            headers: list[JsonValue] = []
            computed: set[int] = set()
            row_dates: list[JsonValue] = []
            for row_index, row in enumerate(sheet.iter_rows(), 1):
                if row_index > 5000 or len(row) > 200:
                    raise AppException(413, "每张工作表最多 5000 行、200 列")
                source_cell_count += len(row)
                if source_cell_count > 100000:
                    raise AppException(413, "原表快照最多保留100000个单元格")
                source_grid.append(
                    [
                        cell.value.isoformat()
                        if isinstance(cell.value, (date, datetime))
                        else cell.value
                        if isinstance(cell.value, (str, int, float, bool))
                        or cell.value is None
                        else str(cell.value)
                        for cell in row
                    ]
                )
                if row_index == 1:
                    headers = [str(cell.value or "") for cell in row]
                    computed.update(calculated_columns(sheet.title, headers))
                if row_index == 2 and sheet.title == "日总量":
                    for index, cell in enumerate(row):
                        if cell.value is not None and index < len(headers):
                            headers[index] = str(cell.value)
                day = parse_source_date(row[0].value if row else None, year)
                if day and not in_import_period(day, start_date, end_date):
                    computed.update(
                        cell.column
                        for cell in row
                        if cell.data_type == "f" and isinstance(cell.column, int)
                    )
                    continue
                if day:
                    row_dates.append({"row": row_index, "date": day.isoformat()})
                for cell in row:
                    if cell.data_type == "f":
                        if isinstance(cell.column, int):
                            computed.add(cell.column)
                        if day and len(formulas) < 10000:
                            formulas.append(
                                {
                                    "sheet": sheet.title,
                                    "cell": cell.coordinate,
                                    "formula": str(cell.value),
                                    "date": day.isoformat() if day else None,
                                }
                            )
                    elif (
                        day
                        and cell.value is not None
                        and isinstance(cell.column, int)
                        and cell.column > 1
                    ):
                        try:
                            value = Decimal(str(cell.value).strip())
                        except InvalidOperation:
                            warnings.append(f"{sheet.title}!{cell.coordinate} 不是数值")
                            continue
                        if value.is_finite():
                            cells.append(
                                {
                                    "date": day.isoformat(),
                                    "column": cell.column,
                                    "value": str(value),
                                    "cell": cell.coordinate,
                                }
                            )
            sheets.append(
                {
                    "name": sheet.title,
                    "category": SOURCE_CATEGORIES.get(sheet.title),
                    "headers": headers,
                    "cells": cells,
                    "row_dates": row_dates,
                    "source_grid": source_grid,
                    "calculated_columns": [column for column in sorted(computed)],
                    "input_columns": [
                        column
                        for column in range(2, len(headers) + 1)
                        if input_column_allowed(sheet.title, headers, column, computed)
                    ],
                }
            )
    finally:
        workbook.close()
    return {
        "year": year,
        "policy_version": IMPORT_POLICY_VERSION,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "sheets": sheets,
        "formulas": formulas,
        "warnings": warnings,
        "notes": [
            "原表逐格保留日期引用、公式与手填值；21表按原公式计算，结果值不重复导入原始计量点。",
            "原始字段及固定公式从工作簿识别，请核对来源列与公式识别结果。",
            "大罐数量不属于导入或填报项目。",
            *(
                ["文件未保留公式；结果表仅作核对，不作为人工修正或原始读数导入。"]
                if not formulas
                else []
            ),
        ],
    }


async def preview_import(
    service: EnergyLedgerService,
    content: bytes,
    year: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ImportResponse:
    validate_import_period(start_date, end_date)
    await service.require_manager()
    await service.repo.serialize_write()
    digest = hashlib.sha256(
        f"{IMPORT_POLICY_VERSION}:{year}:{start_date}:{end_date}:".encode() + content
    ).hexdigest()
    existing = await service.db.scalar(
        select(EnergyImportBatch).where(EnergyImportBatch.content_hash == digest)
    )
    if existing:
        return ImportResponse(
            id=existing.id, status=existing.status, payload=existing.payload
        )
    from asyncio import to_thread

    payload = await to_thread(inspect_xlsx, content, year, start_date, end_date)
    item = EnergyImportBatch(
        id=uuid4(),
        content_hash=digest,
        status="preview",
        payload=payload,
        created_by=service.actor_id,
    )
    service.db.add(item)
    await service.db.flush()
    return ImportResponse(id=item.id, status=item.status, payload=item.payload)


async def confirm_import(
    service: EnergyLedgerService, batch_id: UUID, payload: ImportConfirm
) -> ImportResponse:
    await service.require_manager()
    await service.repo.serialize_write()
    batch = await service.repo.get(EnergyImportBatch, batch_id)
    confirmation = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    confirmations = batch.payload.get("confirmations", [])
    if isinstance(confirmations, list) and confirmation in confirmations:
        return ImportResponse(id=batch.id, status=batch.status, payload=batch.payload)
    keys = [(mapping.sheet, mapping.column) for mapping in payload.mappings]
    if len(set(keys)) != len(keys) or len(
        {mapping.point_id for mapping in payload.mappings}
    ) != len(keys):
        raise AppException(422, "来源列和目标计量点必须一一对应")
    sheets = batch.payload.get("sheets", [])
    if not isinstance(sheets, list):
        raise AppException(422, "导入预览已失效")
    start_value, end_value = (
        batch.payload.get("start_date"),
        batch.payload.get("end_date"),
    )
    start_date = (
        date.fromisoformat(start_value) if isinstance(start_value, str) else None
    )
    end_date = date.fromisoformat(end_value) if isinstance(end_value, str) else None
    validate_import_period(start_date, end_date)
    values: dict[tuple[str, date], list[DirectReadingValue]] = {}
    for mapping in payload.mappings:
        meter = await service.repo.get(EnergyMeterPoint, mapping.point_id)
        definition = MeterDefinition.model_validate(meter.definition)
        source = next(
            (
                sheet
                for sheet in sheets
                if isinstance(sheet, dict) and sheet.get("name") == mapping.sheet
            ),
            None,
        )
        if source is None or mapping.sheet not in SOURCE_CATEGORIES:
            raise AppException(422, "只能导入六类原始填写表，汇总表仅作核对")
        headers = source.get("headers")
        computed_values = source.get("calculated_columns", [])
        computed = (
            {column for column in computed_values if isinstance(column, int)}
            if isinstance(computed_values, list)
            else set()
        )
        if not isinstance(headers, list) or not input_column_allowed(
            mapping.sheet, headers, mapping.column, computed
        ):
            raise AppException(422, "所选列属于自动计算或待确认字段，不能导入原始读数")
        if SOURCE_CATEGORIES[mapping.sheet] != definition.category:
            raise AppException(422, "来源与计量点的能源类别不一致")
        expected_type = "direct" if mapping.sheet == "电量" else "counter"
        if definition.reading_type != expected_type:
            raise AppException(422, "五类表码须为累计读数，电量须为每日直接用量")
        if (
            definition.source_sheet != mapping.sheet
            or definition.source_column != mapping.column
        ):
            raise AppException(422, "来源与计量点已确认的原表字段不一致")
        cells = source.get("cells", [])
        if not isinstance(cells, list):
            continue
        matched = 0
        for cell in cells:
            if not isinstance(cell, dict) or cell.get("column") != mapping.column:
                continue
            day = date.fromisoformat(str(cell["date"]))
            if not in_import_period(day, start_date, end_date):
                continue
            matched += 1
            value = Decimal(str(cell["value"]))
            if value < 0:
                raise AppException(422, "原始读数不能为负数")
            existing = await service.db.scalar(
                select(EnergyReading).where(
                    EnergyReading.point_id == meter.id,
                    EnergyReading.reading_date == day,
                )
            )
            if existing and existing.value is not None:
                if existing.value != value:
                    raise AppException(
                        409,
                        f"{definition.name} 在 {day} 已有不同数据，导入未写入任何记录",
                    )
                continue
            if existing:
                raise AppException(
                    409, "来源日期已有填写草稿，请先处理草稿后重试导入"
                )
            values.setdefault((mapping.sheet, day), []).append(
                DirectReadingValue(point_id=meter.id, value=value, version=0)
            )
        if not matched:
            raise AppException(422, "选定来源列没有可导入的原始数值")
    from app.modules.energy.ledger_entry import write_entries

    for (dataset, day), entries in values.items():
        await write_entries(
            service,
            DirectReadingWrite(
                dataset=dataset, reading_date=day, values=entries, reason=payload.reason
            ),
            source="import",
        )
    batch.status = "imported"
    batch.payload = {
        **batch.payload,
        "imported_count": int(str(batch.payload.get("imported_count", 0)))
        + sum(len(entries) for entries in values.values()),
        "confirmations": [
            *(confirmations if isinstance(confirmations, list) else []),
            confirmation,
        ],
    }
    service.revision(
        "import",
        batch,
        1,
        {
            "mappings": [item.model_dump(mode="json") for item in payload.mappings],
            "imported_count": sum(len(entries) for entries in values.values()),
        },
        payload.reason,
    )
    await service.db.flush()
    return ImportResponse(id=batch.id, status=batch.status, payload=batch.payload)


async def prepare_import(
    service: EnergyLedgerService, batch_id: UUID
) -> "TemplateDraftResponse":
    from app.modules.energy.ledger_models import EnergyCalculationRule
    from app.modules.energy.ledger_schemas import RuleDefinition
    from app.modules.energy.ledger_template import extract_template

    await service.require_manager()
    await service.repo.serialize_write()
    batch = await service.repo.get(EnergyImportBatch, batch_id)
    try:
        draft = extract_template(batch.payload)
    except ValueError as exc:
        raise AppException(422, "无法识别工作簿字段和公式") from exc
    points = await service.repo.all(EnergyMeterPoint)
    rules = await service.repo.all(EnergyCalculationRule)
    codes: dict[str, str] = {}
    for field in draft.meters:
        existing_meter = next(
            (
                item
                for item in points
                if item.definition.get("source_sheet") == field.source_sheet
                and item.definition.get("source_column") == field.source_column
            ),
            None,
        )
        if existing_meter:
            codes["point:" + field.code] = "point:" + existing_meter.code
            continue
        field_values = field.model_dump()
        field_values.update(
            enabled=True,
            active_from=date(2000, 1, 1),
            active_to=None,
        )
        new_meter = EnergyMeterPoint(
            id=uuid4(),
            code=field.code,
            version=1,
            definition=MeterDefinition.model_validate(field_values).model_dump(
                mode="json"
            ),
            created_by=service.actor_id,
        )
        service.db.add(new_meter)
        points.append(new_meter)
        service.revision("meter", new_meter, 1, new_meter.definition, "Excel 原始字段")
        codes["point:" + field.code] = "point:" + new_meter.code
    for formula in draft.rules:
        existing_rule = next(
            (
                item
                for item in rules
                if item.definition.get("source_sheet") == formula.source_sheet
                and item.definition.get("source_column") == formula.source_column
            ),
            None,
        )
        if existing_rule:
            codes["rule:" + formula.code] = "rule:" + existing_rule.code
            continue
        formula_values = formula.model_dump()
        formula_values.update(
            enabled=True,
            active_from=date(2000, 1, 1),
            active_to=None,
        )
        formula_values["terms"] = [
            dict(term, metric_key=codes.get(term["metric_key"], term["metric_key"]))
            for term in formula_values["terms"]
        ]
        new_rule = EnergyCalculationRule(
            id=uuid4(),
            code=formula.code,
            version=1,
            definition=RuleDefinition.model_validate(formula_values).model_dump(
                mode="json"
            ),
            created_by=service.actor_id,
        )
        service.db.add(new_rule)
        rules.append(new_rule)
        service.revision("rule", new_rule, 1, new_rule.definition, "Excel 固定公式")
        codes["rule:" + formula.code] = "rule:" + new_rule.code
    await service.db.flush()
    return draft
