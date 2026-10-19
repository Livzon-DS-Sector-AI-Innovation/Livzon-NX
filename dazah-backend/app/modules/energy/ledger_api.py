"""Native entry API. Archived Wiki routes retain their existing semantics."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.energy.ledger_imports import (
    confirm_import,
    preview_import,
    preview_snapshot_import,
)
from app.modules.energy.ledger_models import EnergyNotificationRun
from app.modules.energy.ledger_notifications import read_bot, save_bot
from app.modules.energy.ledger_schemas import (
    AdjustmentWrite,
    BotResponse,
    BotWrite,
    EnergyMetricOption,
    EntrySubmission,
    GenerateTasks,
    ImportConfirm,
    ImportResponse,
    LedgerOptions,
    LockResponse,
    LockWrite,
    MeterDefinition,
    MeterResponse,
    MeterWrite,
    NotificationResponse,
    PlanResponse,
    PlanWrite,
    ReportResponse,
    ReportScope,
    RevisionResponse,
    RuleDefinition,
    RuleResponse,
    RuleWrite,
    SnapshotImportOption,
    SnapshotImportRequest,
    TaskResponse,
    TrialRequest,
    UsageRow,
    WorkbookDataset,
    WorkbookReport,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_template import TemplateDraftResponse, extract_template
from app.modules.energy.ledger_workbook import DATASETS, EnergyWorkbookService
from app.modules.energy.schemas import EnergyApiResponse
from app.platform.identity.deps import RequiredUser
from app.platform.identity.public_api import list_active_user_options

router = APIRouter()


def ledger_service(
    user: RequiredUser, db: AsyncSession = Depends(get_db)
) -> EnergyLedgerService:
    return EnergyLedgerService(db, user)


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class TrialValue(BaseModel):
    metric_key: str
    name: str
    value: str | None
    status: str


class TrialResponse(BaseModel):
    usage_date: date
    values: list[TrialValue]


class RebuildRequest(BaseModel):
    start_date: date
    end_date: date


@router.get("/ledger-options", response_model=EnergyApiResponse[LedgerOptions])
async def options(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    manager = await service.is_manager()
    people = await list_active_user_options(service.db) if manager else []
    return success_response(
        LedgerOptions(
            is_manager=manager,
            people=[
                {
                    "id": str(person.id),
                    "name": person.name,
                    "department": person.department,
                }
                for person in people
            ],
        ).model_dump(mode="json")
    )


@router.get("/meter-points", response_model=EnergyApiResponse[list[MeterResponse]])
async def meters(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        [item.model_dump(mode="json") for item in await service.meters()]
    )


@router.post("/meter-points", response_model=EnergyApiResponse[MeterResponse])
async def create_meter(
    payload: MeterWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.save_meter(payload)).model_dump(mode="json"))


@router.put(
    "/meter-points/{record_id}", response_model=EnergyApiResponse[MeterResponse]
)
async def update_meter(
    record_id: UUID,
    payload: MeterWrite,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await service.save_meter(payload, record_id)).model_dump(mode="json")
    )


@router.get("/calculation-rules", response_model=EnergyApiResponse[list[RuleResponse]])
async def rules(service: EnergyLedgerService = Depends(ledger_service)) -> JSONResponse:
    return success_response(
        [item.model_dump(mode="json") for item in await service.rules()]
    )


@router.post("/calculation-rules", response_model=EnergyApiResponse[RuleResponse])
async def create_rule(
    payload: RuleWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.save_rule(payload)).model_dump(mode="json"))


@router.put(
    "/calculation-rules/{record_id}", response_model=EnergyApiResponse[RuleResponse]
)
async def update_rule(
    record_id: UUID,
    payload: RuleWrite,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await service.save_rule(payload, record_id)).model_dump(mode="json")
    )


@router.post(
    "/calculation-rules/trial", response_model=EnergyApiResponse[TrialResponse]
)
async def trial(
    payload: TrialRequest, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    await service.require_manager()
    result = await service.evaluate(payload.usage_date)
    return success_response(
        TrialResponse(
            usage_date=payload.usage_date,
            values=[
                TrialValue(
                    metric_key=key,
                    name=definition.name,
                    value=str(value.value) if value.value is not None else None,
                    status=value.status,
                )
                for key, definition, value in result
            ],
        ).model_dump(mode="json")
    )


@router.get("/entry-plans", response_model=EnergyApiResponse[list[PlanResponse]])
async def plans(service: EnergyLedgerService = Depends(ledger_service)) -> JSONResponse:
    return success_response(
        [item.model_dump(mode="json") for item in await service.plans()]
    )


@router.post("/entry-plans", response_model=EnergyApiResponse[PlanResponse])
async def create_plan(
    payload: PlanWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.save_plan(payload)).model_dump(mode="json"))


@router.put("/entry-plans/{record_id}", response_model=EnergyApiResponse[PlanResponse])
async def update_plan(
    record_id: UUID,
    payload: PlanWrite,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await service.save_plan(payload, record_id)).model_dump(mode="json")
    )


@router.post(
    "/entry-tasks/generate", response_model=EnergyApiResponse[TaskListResponse]
)
async def generate_tasks(
    payload: GenerateTasks, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    items = await service.generate_tasks(payload.task_date)
    return success_response(
        TaskListResponse(
            items=[await service.task(item.id) for item in items], total=len(items)
        ).model_dump(mode="json")
    )


@router.get("/entry-tasks", response_model=EnergyApiResponse[TaskListResponse])
async def tasks(
    start_date: date,
    end_date: date,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    mine: bool = True,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    items, total = await service.tasks(start_date, end_date, page, page_size, mine)
    return success_response(
        TaskListResponse(items=items, total=total).model_dump(mode="json")
    )


@router.get("/entry-tasks/{task_id}", response_model=EnergyApiResponse[TaskResponse])
async def task(
    task_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.task(task_id)).model_dump(mode="json"))


@router.post(
    "/entry-tasks/{task_id}/submit", response_model=EnergyApiResponse[TaskResponse]
)
async def submit(
    task_id: UUID,
    payload: EntrySubmission,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await service.submit(task_id, payload)).model_dump(mode="json")
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


@router.post("/adjustments", response_model=EnergyApiResponse[UsageRow])
async def adjust(
    payload: AdjustmentWrite, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    return success_response((await service.adjust(payload)).model_dump(mode="json"))


@router.get("/period-locks", response_model=EnergyApiResponse[list[LockResponse]])
async def locks(service: EnergyLedgerService = Depends(ledger_service)) -> JSONResponse:
    return success_response(
        [item.model_dump(mode="json") for item in await service.locks()]
    )


@router.put("/period-locks/{month}", response_model=EnergyApiResponse[LockResponse])
async def set_lock(
    month: str,
    payload: LockWrite,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await service.set_lock(month, payload)).model_dump(mode="json")
    )


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
    "/imports/snapshot-options",
    response_model=EnergyApiResponse[list[SnapshotImportOption]],
)
async def snapshot_options(
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    from app.modules.energy.ledger_imports import SOURCE_CATEGORIES
    from app.modules.energy.models import EnergySheetSnapshot, EnergyWorkbookSheet

    await service.require_manager()
    rows = (
        await service.db.execute(
            select(EnergySheetSnapshot, EnergyWorkbookSheet.title)
            .join(
                EnergyWorkbookSheet,
                EnergyWorkbookSheet.id == EnergySheetSnapshot.sheet_id,
            )
            .where(
                EnergySheetSnapshot.is_deleted.is_(False),
                EnergyWorkbookSheet.is_deleted.is_(False),
                EnergyWorkbookSheet.title.in_(SOURCE_CATEGORIES),
            )
            .order_by(EnergySheetSnapshot.captured_at.desc())
            .limit(500)
        )
    ).all()
    return success_response(
        [
            SnapshotImportOption(
                id=snapshot.id,
                sheet_title=title,
                captured_at=snapshot.captured_at,
                snapshot_number=snapshot.snapshot_number,
            ).model_dump(mode="json")
            for snapshot, title in rows
        ]
    )


@router.post("/imports/from-snapshot", response_model=EnergyApiResponse[ImportResponse])
async def from_snapshot(
    payload: SnapshotImportRequest,
    service: EnergyLedgerService = Depends(ledger_service),
) -> JSONResponse:
    return success_response(
        (await preview_snapshot_import(service, payload)).model_dump(mode="json")
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


@router.post(
    "/imports/{batch_id}/draft-config",
    response_model=EnergyApiResponse[TemplateDraftResponse],
)
async def draft_config(
    batch_id: UUID, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    from app.modules.energy.ledger_models import (
        EnergyCalculationRule,
        EnergyImportBatch,
        EnergyMeterPoint,
    )

    await service.require_manager()
    await service.repo.serialize_write()
    batch = await service.repo.get(EnergyImportBatch, batch_id)
    try:
        draft = extract_template(batch.payload)
    except ValueError as exc:
        raise AppException(422, "无法提取计算关系，请检查工作簿结构") from exc
    existing_points = {item.code for item in await service.repo.all(EnergyMeterPoint)}
    existing_rules = {
        item.code for item in await service.repo.all(EnergyCalculationRule)
    }
    for point in draft.meters:
        if point.code not in existing_points:
            await service.save_meter(MeterWrite(definition=point))
    for rule in draft.rules:
        if rule.code not in existing_rules:
            await service.save_rule(RuleWrite(definition=rule))
    return success_response(draft.model_dump(mode="json"))


@router.post("/reporting/rebuild", response_model=EnergyApiResponse[ReportResponse])
async def rebuild(
    payload: RebuildRequest, service: EnergyLedgerService = Depends(ledger_service)
) -> JSONResponse:
    from datetime import timedelta

    await service.require_manager()
    service.validate_range(payload.start_date, payload.end_date)
    await service.repo.serialize_write()
    await service.rebuild(
        {
            payload.start_date + timedelta(days=index)
            for index in range((payload.end_date - payload.start_date).days + 1)
        }
    )
    return success_response(
        (await service.report(payload.start_date, payload.end_date)).model_dump(
            mode="json"
        )
    )
