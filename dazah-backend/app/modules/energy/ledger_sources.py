"""Select and overlay the original workbook belonging to a reporting month."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import EnergyImportBatch, EnergyReading
from app.modules.energy.ledger_schemas import MeterResponse
from app.modules.energy.ledger_source_workbook import SourceWorkbook, source_period


@dataclass
class MonthlySource:
    workbook: SourceWorkbook
    batch_id: UUID
    created_at: datetime


async def load_monthly_source(
    db: AsyncSession, year: int, month: int, meters: list[MeterResponse]
) -> MonthlySource | None:
    period_text = f"{year:04}-{month:02}"
    batches = (
        await db.scalars(
            select(EnergyImportBatch)
            .where(
                EnergyImportBatch.is_deleted.is_(False),
                EnergyImportBatch.status == "imported",
                (EnergyImportBatch.payload["report_period"].astext == period_text)
                | EnergyImportBatch.payload["report_period"].astext.is_(None),
            )
            .order_by(EnergyImportBatch.created_at.desc(), EnergyImportBatch.id.desc())
            .limit(1001)
        )
    ).all()
    if len(batches) > 1000:
        raise AppException(422, "历史导入批次过多，请先核对原表月份")
    selected: MonthlySource | None = None
    for batch in batches:
        try:
            if source_period(batch.payload) != (year, month):
                continue
            book = SourceWorkbook.from_payload(batch.payload, period=(year, month))
        except ValueError as exc:
            raise AppException(409, "原表日期或快照无效，请核对对应月份的文件") from exc
        if book.sheets:
            selected = MonthlySource(book, batch.id, batch.created_at)
            break
    if selected is None:
        return None
    from app.modules.energy.ledger_fields import find_field

    selected.workbook.require_inputs(
        {
            (str(field["source_sheet"]), int(str(field["source_column"])))
            for field in selected.workbook.field_mappings
            if field["kind"] == "reading"
        }
    )
    start = date(year, month, 1) - timedelta(days=32)
    end = date(year, month, monthrange(year, month)[1]) + timedelta(days=32)
    definitions = {meter.id: meter.definition for meter in meters}
    readings = (
        await db.scalars(
            select(EnergyReading)
            .where(
                EnergyReading.point_id.in_(definitions),
                EnergyReading.reading_date.between(start, end),
                EnergyReading.is_deleted.is_(False),
                EnergyReading.value.is_not(None),
            )
            .order_by(EnergyReading.reading_date, EnergyReading.point_id)
        )
    ).all()
    for reading in readings:
        if (
            reading.value is None
            or reading.submitted_at is None
            or reading.submitted_at < selected.created_at
            or (
                reading.source == "import"
                and (reading.reading_date.year, reading.reading_date.month)
                != (year, month)
            )
        ):
            continue
        definition = definitions[reading.point_id]
        if definition.source_column:
            field = find_field(selected.workbook.field_mappings, definition)
            try:
                selected.workbook.set_reading(
                    str(field["source_sheet"]) if field else definition.source_sheet,
                    int(str(field["source_column"]))
                    if field
                    else definition.source_column,
                    reading.reading_date,
                    reading.value,
                    version=reading.version,
                )
            except ValueError as exc:
                raise AppException(
                    409, "原始读数来源与原表公式冲突，请核对导入版本"
                ) from exc
    return selected
