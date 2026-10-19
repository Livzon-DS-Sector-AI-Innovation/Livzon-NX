"""Bounded XLSX preview; source literals are imported only after explicit mapping."""

import hashlib
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

import openpyxl
from openpyxl.utils.datetime import from_excel
from pydantic import JsonValue
from sqlalchemy import select

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import (
    EnergyEntryPlan,
    EnergyEntryTask,
    EnergyImportBatch,
    EnergyMeterPoint,
    EnergyReading,
)
from app.modules.energy.ledger_schemas import (
    EntrySubmission,
    EntryValue,
    ImportConfirm,
    ImportResponse,
    MeterDefinition,
    SnapshotImportRequest,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_source_policy import (
    SOURCE_CATEGORIES as SOURCE_CATEGORIES,
)
from app.modules.energy.ledger_source_policy import (
    calculated_columns as calculated_columns,
)
from app.modules.energy.ledger_source_policy import (
    input_column_allowed as input_column_allowed,
)

IMPORT_POLICY_VERSION = 2


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
    try:
        for sheet in workbook:
            sheet.reset_dimensions()
            cells: list[JsonValue] = []
            headers: list[JsonValue] = []
            computed: set[int] = set()
            row_dates: list[JsonValue] = []
            for row_index, row in enumerate(sheet.iter_rows(), 1):
                if row_index > 5000 or len(row) > 200:
                    raise AppException(413, "每张工作表最多 5000 行、200 列")
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
            "表码按实际日期计算；公式仅用于核对，不作为原始用量重复导入。",
            "单位、倍率、共享关系及跨行公式须在配置草案中核对后启用。",
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
    if any(
        not in_import_period(item.usage_date, start_date, end_date)
        for item in payload.adjustments
    ):
        raise AppException(422, "人工修正日期超出本次有效导入范围")
    values: dict[date, list[tuple[UUID, Decimal, date]]] = {}
    for mapping in payload.mappings:
        meter = await service.repo.get(EnergyMeterPoint, mapping.point_id)
        definition = MeterDefinition.model_validate(meter.definition)
        if not definition.enabled:
            raise AppException(422, "请先确认并启用映射的计量点，再导入历史数据")
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
        if definition.source_sheet and (
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
                    409, "来源日期已有未完成任务，请先完成该任务后重试导入"
                )
            task_day = (
                day + timedelta(days=1) if definition.reading_type == "direct" else day
            )
            values.setdefault(task_day, []).append((meter.id, value, day))
        if not matched:
            raise AppException(422, "选定来源列没有可导入的原始数值")
    # Dedicated non-scheduled plan retains responsibility and correction access.
    plan = EnergyEntryPlan(
        id=uuid4(),
        version=1,
        definition={
            "name": "历史导入",
            "point_ids": [str(item.point_id) for item in payload.mappings],
            "owner_ids": [str(service.actor_id)],
            "publish_time": "08:00",
            "deadline_time": "10:00",
            "reminder_time": "10:30",
            "group_chat_id": "",
            "enabled": False,
        },
        created_by=service.actor_id,
    )
    if values:
        service.db.add(plan)
    for task_day, entries in values.items():
        task = EnergyEntryTask(
            id=uuid4(),
            plan_id=plan.id,
            task_date=task_day,
            definition={**plan.definition, "plan_version": 1},
            created_by=service.actor_id,
        )
        service.db.add(task)
        writes: list[EntryValue] = []
        for point_id, value, day in entries:
            reading = EnergyReading(
                id=uuid4(),
                task_id=task.id,
                point_id=point_id,
                reading_date=day,
                version=0,
                source="import",
                exception={},
            )
            service.db.add(reading)
            writes.append(EntryValue(reading_id=reading.id, version=0, value=value))
        await service.db.flush()
        await service.submit(
            task.id,
            EntrySubmission(values=writes, reason=payload.reason),
            imported=True,
        )
    for adjustment in payload.adjustments:
        await service.adjust(adjustment)
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


async def preview_snapshot_import(
    service: EnergyLedgerService, payload: SnapshotImportRequest
) -> ImportResponse:
    from app.modules.energy.models import (
        EnergySheetSnapshot,
        EnergySnapshotRow,
        EnergyWorkbookSheet,
    )

    validate_import_period(payload.start_date, payload.end_date)
    await service.require_manager()
    await service.repo.serialize_write()
    sheets: list[JsonValue] = []
    source_hashes: list[str] = []
    titles: set[str] = set()
    for snapshot_id in payload.snapshot_ids:
        snapshot = await service.db.get(EnergySheetSnapshot, snapshot_id)
        sheet = (
            await service.db.get(EnergyWorkbookSheet, snapshot.sheet_id)
            if snapshot
            else None
        )
        if snapshot is None or sheet is None or snapshot.is_deleted or sheet.is_deleted:
            raise AppException(404, "历史快照不存在")
        if sheet.title not in SOURCE_CATEGORIES or sheet.title in titles:
            raise AppException(422, "每类原始表只能选择一份快照，不导入汇总快照")
        titles.add(sheet.title)
        if snapshot.row_count > 5000 or len(snapshot.header_values) > 200:
            raise AppException(413, "历史快照超过单次处理上限")
        rows = list(
            (
                await service.db.scalars(
                    select(EnergySnapshotRow)
                    .where(EnergySnapshotRow.snapshot_id == snapshot.id)
                    .order_by(EnergySnapshotRow.row_index)
                    .limit(5001)
                )
            ).all()
        )
        cells: list[JsonValue] = []
        headers: list[JsonValue] = [header for header in snapshot.header_values]
        computed = calculated_columns(sheet.title, headers)
        for row in rows:
            day = parse_source_date(row.values[0] if row.values else None, payload.year)
            if day is None or not in_import_period(
                day, payload.start_date, payload.end_date
            ):
                continue
            for column, raw in enumerate(row.values[1:], 2):
                if raw is None or isinstance(raw, bool) or column in computed:
                    continue
                try:
                    value = Decimal(str(raw))
                except InvalidOperation:
                    continue
                if value.is_finite():
                    cells.append(
                        {
                            "date": day.isoformat(),
                            "column": column,
                            "value": str(value),
                            "cell": f"row-{row.row_index}-col-{column}",
                        }
                    )
        sheets.append(
            {
                "name": sheet.title,
                "category": SOURCE_CATEGORIES[sheet.title],
                "headers": headers,
                "cells": cells,
                "calculated_columns": [column for column in sorted(computed)],
                "input_columns": [
                    column
                    for column in range(2, len(headers) + 1)
                    if input_column_allowed(sheet.title, headers, column, computed)
                ],
                "snapshot_id": str(snapshot.id),
            }
        )
        source_hashes.append(f"{snapshot.id}:{snapshot.content_hash}")
    digest = hashlib.sha256(
        (
            f"{IMPORT_POLICY_VERSION}:{payload.year}:"
            f"{payload.start_date}:{payload.end_date}:"
            + ":".join(sorted(source_hashes))
        ).encode()
    ).hexdigest()
    existing = await service.db.scalar(
        select(EnergyImportBatch).where(EnergyImportBatch.content_hash == digest)
    )
    if existing:
        return ImportResponse(
            id=existing.id, status=existing.status, payload=existing.payload
        )
    item = EnergyImportBatch(
        id=uuid4(),
        content_hash=digest,
        status="preview",
        payload={
            "year": payload.year,
            "policy_version": IMPORT_POLICY_VERSION,
            "start_date": payload.start_date.isoformat()
            if payload.start_date
            else None,
            "end_date": payload.end_date.isoformat() if payload.end_date else None,
            "sheets": sheets,
            "formulas": [],
            "warnings": [
                "历史快照不包含可靠的公式来源，汇总计算关系须在配置中单独核对。"
            ],
            "source_snapshot_ids": [str(value) for value in payload.snapshot_ids],
        },
        created_by=service.actor_id,
    )
    service.db.add(item)
    await service.db.flush()
    return ImportResponse(id=item.id, status=item.status, payload=item.payload)
