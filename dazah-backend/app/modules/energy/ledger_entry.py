"""Direct original-sheet entry, independent of plans, tasks and closing periods."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select

from app.core.exceptions import AppException
from app.modules.energy.ledger_models import EnergyReading
from app.modules.energy.ledger_schemas import (
    DirectReadingItem,
    DirectReadingResponse,
    DirectReadingWrite,
    MeterResponse,
)
from app.modules.energy.ledger_service import EnergyLedgerService, affected_dates
from app.modules.energy.ledger_source_policy import (
    SOURCE_CATEGORIES,
    manual_input_allowed,
)


async def source_fields(
    service: EnergyLedgerService, dataset: str
) -> list[MeterResponse]:
    if dataset not in SOURCE_CATEGORIES:
        raise AppException(422, "仅支持五类表码与原始电量，自动计算表不能填写")
    fields = [
        item
        for item in await service.meters()
        if item.definition.source_sheet == dataset
        and "大罐数量" not in item.definition.name
        and manual_input_allowed(
            dataset,
            item.definition.name,
            item.definition.reading_type,
            item.definition.category,
        )
    ]
    return sorted(
        fields,
        key=lambda item: (item.definition.source_column or 0, item.definition.code),
    )


async def read_entries(
    service: EnergyLedgerService, day: date, dataset: str
) -> DirectReadingResponse:
    fields = await source_fields(service, dataset)
    rows = list(
        (
            await service.db.scalars(
                select(EnergyReading).where(
                    EnergyReading.point_id.in_([item.id for item in fields]),
                    EnergyReading.reading_date == day,
                    EnergyReading.is_deleted.is_(False),
                )
            )
        ).all()
    )
    readings = {item.point_id: item for item in rows}
    return DirectReadingResponse(
        reading_date=day,
        dataset=dataset,
        items=[
            DirectReadingItem(
                point_id=item.id,
                name=item.definition.name,
                unit=item.definition.unit,
                precision=item.definition.precision,
                reading_id=readings[item.id].id if item.id in readings else None,
                value=readings[item.id].value if item.id in readings else None,
                draft_value=readings[item.id].draft_value
                if item.id in readings
                else None,
                version=readings[item.id].version if item.id in readings else 0,
            )
            for item in fields
        ],
    )


async def write_entries(
    service: EnergyLedgerService,
    payload: DirectReadingWrite,
    *,
    source: str = "platform",
) -> DirectReadingResponse:
    await service.repo.serialize_write()
    fields = {item.id: item for item in await source_fields(service, payload.dataset)}
    existing = {
        item.point_id: item
        for item in (
            await service.db.scalars(
                select(EnergyReading).where(
                    EnergyReading.point_id.in_(
                        [item.point_id for item in payload.values]
                    ),
                    EnergyReading.reading_date == payload.reading_date,
                )
            )
        ).all()
    }
    for entry in payload.values:
        field = fields.get(entry.point_id)
        if field is None:
            raise AppException(403, "字段不属于当前原始表或超出数据权限")
        row = existing.get(entry.point_id)
        if row and row.is_deleted:
            raise AppException(409, "原始记录已作废，请刷新后重试")
        if entry.version != (row.version if row else 0):
            raise AppException(409, "数据已被修改，请刷新后核对最新版本")
        if entry.value != entry.value.quantize(
            Decimal(1).scaleb(-field.definition.precision)
        ):
            raise AppException(
                422,
                f"{field.definition.name} 最多保留 {field.definition.precision} 位小数",
            )
        if (
            row
            and row.value is not None
            and row.value != entry.value
            and not payload.draft
            and not payload.reason
        ):
            raise AppException(422, "更正已生效数据必须填写原因")
    days: set[date] = set()
    for entry in payload.values:
        row = existing.get(entry.point_id)
        if (
            row
            and (row.draft_value if payload.draft else row.value) == entry.value
            and (payload.draft or row.draft_value is None)
        ):
            continue
        if row is None:
            row = EnergyReading(
                id=uuid4(),
                point_id=entry.point_id,
                reading_date=payload.reading_date,
                # Retained historical column; now only identifies a write batch.
                task_id=uuid5(
                    NAMESPACE_URL,
                    f"energy-sheet:{payload.dataset}:{payload.reading_date}",
                ),
                version=0,
                exception={},
                created_by=service.actor_id,
            )
            service.db.add(row)
        before = str(row.value) if row.value is not None else None
        row.version += 1
        row.updated_by = service.actor_id
        row.draft_value = entry.value if payload.draft else None
        if not payload.draft:
            row.value = entry.value
            row.source = source
            row.submitted_at = datetime.now(UTC)
            days.update(
                affected_dates(payload.reading_date, fields[entry.point_id].definition)
            )
        service.revision(
            "reading",
            row,
            row.version,
            {
                "before": before,
                "value": str(entry.value),
                "draft": payload.draft,
                "source": source,
                "dataset": payload.dataset,
                "reading_date": str(payload.reading_date),
            },
            payload.reason,
        )
    await service.db.flush()
    if days:
        await service.rebuild(days)
        from app.modules.energy.ledger_notifications import enqueue_reading_notification

        versions = ":".join(
            f"{item.point_id}-{item.version}" for item in payload.values
        )
        await enqueue_reading_notification(
            service.db,
            service.actor_id,
            payload.dataset,
            str(payload.reading_date),
            versions,
            len(payload.values),
        )
    return await read_entries(service, payload.reading_date, payload.dataset)
