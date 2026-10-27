"""Native ledger API for entry, reporting, imports and reviews."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.energy.ledger_imports import confirm_import, preview_import
from app.modules.energy.ledger_models import (
    EnergyLedgerRevision,
    EnergyNotificationRun,
)
from app.modules.energy.ledger_notifications import read_bot, save_bot
from app.modules.energy.ledger_reviews import (
    load_usage_review_records,
    save_usage_reviews,
)
from app.modules.energy.ledger_schemas import (
    BotResponse,
    BotWrite,
    DirectReadingResponse,
    DirectReadingWrite,
    EnergyMetricOption,
    ImportConfirm,
    ImportResponse,
    LedgerOptions,
    MeterDefinition,
    MeterResponse,
    NotificationResponse,
    ReportResponse,
    ReportScope,
    RevisionResponse,
    RuleDefinition,
    UsageReview,
    UsageReviewResponse,
    UsageReviewUpdate,
    UsageRow,
    WorkbookDataset,
    WorkbookReport,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_template import TemplateDraftResponse
from app.modules.energy.ledger_workbook import DATASETS, EnergyWorkbookService
from app.modules.energy.schemas import EnergyApiResponse
from app.platform.identity.deps import RequiredUser

router = APIRouter()


def ledger_service(
    user: RequiredUser, db: AsyncSession = Depends(get_db)
) -> EnergyLedgerService:
    return EnergyLedgerService(db, user)


def _review_responses(
    records: list[EnergyLedgerRevision],
) -> list[UsageReviewResponse]:
    responses: list[UsageReviewResponse] = []
    for record in records:
        review = UsageReview.model_validate(record.payload)
        if not review.periods:
            continue
        responses.append(
            UsageReviewResponse(
                **review.model_dump(),
                updated_at=record.created_at,
                updated_by=record.created_by,
            )
        )
    return responses


@router.get("/ledger-options", response_model=EnergyApiResponse[LedgerOptions])
async def options(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        LedgerOptions(is_manager=await service.is_manager(), people=[]).model_dump(
            mode="json"
        )
    )


@router.get("/input-fields", response_model=EnergyApiResponse[list[MeterResponse]])
async def meters(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        [item.model_dump(mode="json") for item in await service.meters()]
    )


@router.get("/reporting", response_model=EnergyApiResponse[ReportResponse])
async def report(
    start_date: date,
    end_date: date,
    report_scope: ReportScope = "detail",
    workshop: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=40),
    metric_key: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    include_basis: bool = False,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (
            await service.report(
                start_date,
                end_date,
                report_scope=report_scope,
                workshop=workshop,
                category=category,
                metric_key=metric_key,
                page=page,
                page_size=page_size,
                include_basis=include_basis,
            )
        ).model_dump(mode="json")
    )


@router.get("/reporting/trace/{fact_id}", response_model=EnergyApiResponse[UsageRow])
async def trace(
    fact_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.trace(fact_id)).model_dump(mode="json"))


@router.get(
    "/reporting/datasets", response_model=EnergyApiResponse[list[WorkbookDataset]]
)
async def workbook_datasets(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response([item.model_dump(mode="json") for item in DATASETS])


@router.get(
    "/reporting/metrics", response_model=EnergyApiResponse[list[EnergyMetricOption]]
)
async def reporting_metrics(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    definitions: list[tuple[str, MeterDefinition | RuleDefinition]] = [
        *(("point:", item.definition) for item in await service.meters()),
        *(("rule:", item.definition) for item in await service.rules()),
    ]
    return success_response(
        [
            EnergyMetricOption(
                metric_key=kind + definition.code,
                name=definition.name,
                category=definition.category,
                unit=definition.unit,
            ).model_dump(mode="json")
            for kind, definition in definitions
            if definition.enabled
        ]
    )


@router.get("/reporting/workbook", response_model=EnergyApiResponse[WorkbookReport])
async def workbook_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    dataset: str = Query(..., max_length=100),
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await EnergyWorkbookService(service).report(year, month, dataset)).model_dump(
            mode="json"
        )
    )


@router.get("/reporting/workbook/export")
async def export_workbook(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    dataset: str | None = Query(None, max_length=100),
    service: EnergyLedgerService = Depends(ledger_service),
) -> Response:
    from asyncio import to_thread

    from app.modules.energy.ledger_exports import build_workbook_export

    workbook = EnergyWorkbookService(service)
    sheets = [
        await workbook.report(year, month, name)
        for name in ([dataset] if dataset else [item.name for item in DATASETS])
    ]
    return Response(
        await to_thread(build_workbook_export, sheets),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="energy-workbook-{year}-{month:02d}.xlsx"'
            )
        },
    )


@router.get("/reporting/export")
async def export_report(
    start_date: date,
    end_date: date,
    report_scope: ReportScope = "detail",
    workshop: str | None = None,
    category: str | None = None,
    metric_key: str | None = Query(None, max_length=100),
    service: EnergyLedgerService = Depends(ledger_service),
) -> Response:
    report = await service.report(
        start_date,
        end_date,
        report_scope=report_scope,
        workshop=workshop,
        category=category,
        metric_key=metric_key,
        include_all=True,
    )
    from asyncio import to_thread

    import openpyxl

    def build() -> bytes:
        workbook = openpyxl.Workbook(write_only=True)
        sheet = workbook.create_sheet("能源报表")
        sheet.append(
            ["日期", "指标", "能源", "车间", "温度", "单位", "计算值", "有效值", "状态"]
        )
        for row in report.rows:
            # Preserve text as text, including formula-like external names.
            from openpyxl.cell import WriteOnlyCell

            def numeric(value: Decimal | None) -> float | str | None:
                if value is None:
                    return None
                return (
                    float(value)
                    if len(value.normalize().as_tuple().digits) <= 15
                    else str(value)
                )

            values: list[str | float | datetime | None] = [
                datetime.combine(row.usage_date, datetime.min.time()),
                row.name,
                row.category,
                row.workshop,
                row.temperature,
                row.unit,
                numeric(row.calculated_value),
                numeric(row.effective_value),
                row.status,
            ]
            cells = []
            for value in values:
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    return Response(
        await to_thread(build),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="energy-{start_date}-{end_date}.xlsx"'
            )
        },
    )


@router.get("/data-quality", response_model=EnergyApiResponse[ReportResponse])
async def quality(
    start_date: date,
    end_date: date,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    workshop: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=40),
    quality_status: str | None = Query(None, max_length=40),
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    data = await service.report(
        start_date,
        end_date,
        report_scope="all",
        include_all=True,
        workshop=workshop,
        category=category,
    )
    data.rows = [
        row
        for row in data.rows
        if row.status not in {"complete", "adjusted"} or row.provenance.get("late")
    ]
    from collections import Counter

    data.quality_counts = dict(
        Counter(
            row.status
            if row.status not in {"complete", "adjusted"}
            else "late_submission"
            for row in data.rows
        )
    )
    if quality_status:
        data.rows = [
            row
            for row in data.rows
            if row.status == quality_status
            or (quality_status == "late_submission" and row.provenance.get("late"))
        ]
    data.total_count = len(data.rows)
    data.rows = data.rows[(page - 1) * page_size : page * page_size]
    return success_response(data.model_dump(mode="json"))


@router.get(
    "/ledger-history/{kind}/{entity_id}",
    response_model=EnergyApiResponse[list[RevisionResponse]],
)
async def history(
    kind: str, entity_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response(
        [
            item.model_dump(mode="json")
            for item in await service.history(kind, entity_id)
        ]
    )


@router.get("/bot-config", response_model=EnergyApiResponse[BotResponse])
async def get_bot(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    await service.require_manager()
    return success_response((await read_bot(service.db)).model_dump(mode="json"))


@router.put("/bot-config", response_model=EnergyApiResponse[BotResponse])
async def put_bot(
    payload: BotWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    await service.require_manager()
    await service.repo.serialize_write()
    return success_response(
        (await save_bot(service.db, payload, service.actor_id)).model_dump(mode="json")
    )


@router.get(
    "/notification-runs", response_model=EnergyApiResponse[list[NotificationResponse]]
)
async def notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    await service.require_manager()
    rows = (
        await service.db.scalars(
            select(EnergyNotificationRun)
            .order_by(EnergyNotificationRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return success_response(
        [
            NotificationResponse.model_validate(item, from_attributes=True).model_dump(
                mode="json"
            )
            for item in rows
        ]
    )


@router.post(
    "/notification-runs/{record_id}/retry",
    response_model=EnergyApiResponse[NotificationResponse],
)
async def retry_notification(
    record_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    await service.require_manager()
    await service.repo.serialize_write()
    run = await service.repo.get(EnergyNotificationRun, record_id)
    if run.status not in {"failed", "retry"}:
        raise AppException(409, "只有失败或待重试的消息可重试")
    service.revision(
        "notification",
        run,
        run.attempts + 1,
        {"previous_status": run.status, "previous_attempts": run.attempts},
        "人工重试消息",
    )
    run.status, run.attempts, run.next_attempt_at = "pending", 0, None
    await service.db.flush()
    return success_response(
        NotificationResponse.model_validate(run, from_attributes=True).model_dump(
            mode="json"
        )
    )


@router.get(
    "/usage-reviews", response_model=EnergyApiResponse[list[UsageReviewResponse]]
)
async def list_usage_reviews(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    await service.require_manager()
    records = await load_usage_review_records(service)
    return success_response(
        [item.model_dump(mode="json") for item in _review_responses(records)]
    )


@router.put(
    "/usage-reviews", response_model=EnergyApiResponse[list[UsageReviewResponse]]
)
async def update_usage_reviews(
    payload: UsageReviewUpdate,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    await save_usage_reviews(service, payload.reviews, payload.reason)
    records = await load_usage_review_records(service)
    return success_response(
        [item.model_dump(mode="json") for item in _review_responses(records)]
    )


@router.post("/imports/preview", response_model=EnergyApiResponse[ImportResponse])
async def import_preview(
    year: int = Query(..., ge=2000, le=2100),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    file: UploadFile = File(...),
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    if (
        not file.filename
        or not file.filename.lower().endswith(".xlsx")
        or file.content_type
        not in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream",
            "application/zip",
        }
    ):
        raise AppException(422, "请上传 XLSX 格式文件")
    content = await file.read(10 * 1024 * 1024 + 1)
    return success_response(
        (await preview_import(service, content, year, start_date, end_date)).model_dump(
            mode="json"
        )
    )


@router.post(
    "/imports/{batch_id}/confirm", response_model=EnergyApiResponse[ImportResponse]
)
async def import_confirm(
    batch_id: UUID,
    payload: ImportConfirm,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await confirm_import(service, batch_id, payload)).model_dump(mode="json")
    )


@router.get("/input-readings", response_model=EnergyApiResponse[DirectReadingResponse])
async def input_readings(
    reading_date: date,
    dataset: str = Query(..., max_length=100),
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    from app.modules.energy.ledger_entry import read_entries

    return success_response(
        (await read_entries(service, reading_date, dataset)).model_dump(mode="json")
    )


@router.put("/input-readings", response_model=EnergyApiResponse[DirectReadingResponse])
async def save_input_readings(
    payload: DirectReadingWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    from app.modules.energy.ledger_entry import write_entries

    return success_response(
        (await write_entries(service, payload)).model_dump(mode="json")
    )


@router.post(
    "/imports/{batch_id}/prepare",
    response_model=EnergyApiResponse[TemplateDraftResponse],
)
async def prepare_workbook(
    batch_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    from app.modules.energy.ledger_imports import prepare_import

    return success_response(
        (await prepare_import(service, batch_id)).model_dump(mode="json")
    )
