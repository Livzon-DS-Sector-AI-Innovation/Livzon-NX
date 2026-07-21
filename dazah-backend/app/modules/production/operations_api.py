"""发酵、种子培养、事件、班次日志和交接确认 API。"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.production.models import (
    FermentationRecord,
    NonConformingEvent,
    SeedCultureRecord,
    ShiftHandover,
    ShiftLog,
)
from app.modules.production.operations_schemas import (
    FermentationCreate,
    FermentationResponse,
    FermentationUpdate,
    NonConformingEventCreate,
    NonConformingEventResponse,
    NonConformingEventUpdate,
    SeedCultureCreate,
    SeedCultureResponse,
    SeedCultureUpdate,
    ShiftHandoverCreate,
    ShiftHandoverResponse,
    ShiftHandoverUpdate,
    ShiftLogCreate,
    ShiftLogResponse,
    ShiftLogUpdate,
)
from app.modules.production.operations_service import OperationsService
from app.modules.production.schemas import ProductionApiResponse

router = APIRouter()


def _actor(user: CurrentUser | None) -> uuid.UUID | None:
    return user.id if user else None


def _page(data: list[Any], schema: type, page: int, page_size: int, total: int):
    return ApiResponse(
        data=[schema.model_validate(item) for item in data],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get(
    "/fermentations", response_model=ProductionApiResponse[list[FermentationResponse]]
)
async def list_fermentations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    rows, total = await OperationsService(db).list_fermentations(
        skip=(page - 1) * page_size, limit=page_size, batch_no=batch_no, status=status
    )
    return _page(rows, FermentationResponse, page, page_size, total)


@router.post(
    "/fermentations", response_model=ProductionApiResponse[FermentationResponse]
)
async def create_fermentation(
    payload: FermentationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).create_fermentation(payload, _actor(current_user))
    await db.commit()
    return ApiResponse(data=FermentationResponse.model_validate(row))


@router.put(
    "/fermentations/{record_id}",
    response_model=ProductionApiResponse[FermentationResponse],
)
async def update_fermentation(
    record_id: uuid.UUID,
    payload: FermentationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).update_fermentation(
        record_id, payload, _actor(current_user)
    )
    if not row:
        return ApiResponse(code=404, message="发酵记录不存在")
    await db.commit()
    return ApiResponse(data=FermentationResponse.model_validate(row))


@router.delete("/fermentations/{record_id}", response_model=ProductionApiResponse[None])
async def delete_fermentation(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await OperationsService(db).delete(FermentationRecord, record_id)
    if not deleted:
        return ApiResponse(code=404, message="发酵记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get(
    "/seed-cultures", response_model=ProductionApiResponse[list[SeedCultureResponse]]
)
async def list_seed_cultures(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    rows, total = await OperationsService(db).list_seed_cultures(
        skip=(page - 1) * page_size, limit=page_size, batch_no=batch_no, status=status
    )
    return _page(rows, SeedCultureResponse, page, page_size, total)


@router.post(
    "/seed-cultures", response_model=ProductionApiResponse[SeedCultureResponse]
)
async def create_seed_culture(
    payload: SeedCultureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).create_seed_culture(payload, _actor(current_user))
    await db.commit()
    return ApiResponse(data=SeedCultureResponse.model_validate(row))


@router.put(
    "/seed-cultures/{record_id}",
    response_model=ProductionApiResponse[SeedCultureResponse],
)
async def update_seed_culture(
    record_id: uuid.UUID,
    payload: SeedCultureUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).update_seed_culture(
        record_id, payload, _actor(current_user)
    )
    if not row:
        return ApiResponse(code=404, message="种子培养记录不存在")
    await db.commit()
    return ApiResponse(data=SeedCultureResponse.model_validate(row))


@router.delete("/seed-cultures/{record_id}", response_model=ProductionApiResponse[None])
async def delete_seed_culture(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await OperationsService(db).delete(SeedCultureRecord, record_id)
    if not deleted:
        return ApiResponse(code=404, message="种子培养记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get(
    "/non-conforming-events",
    response_model=ProductionApiResponse[list[NonConformingEventResponse]],
)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    workshop: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    rows, total = await OperationsService(db).list_events(
        skip=(page - 1) * page_size, limit=page_size, workshop=workshop, status=status
    )
    return _page(rows, NonConformingEventResponse, page, page_size, total)


@router.post(
    "/non-conforming-events",
    response_model=ProductionApiResponse[NonConformingEventResponse],
)
async def create_event(
    payload: NonConformingEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).create_event(payload, _actor(current_user))
    await db.commit()
    return ApiResponse(data=NonConformingEventResponse.model_validate(row))


@router.put(
    "/non-conforming-events/{record_id}",
    response_model=ProductionApiResponse[NonConformingEventResponse],
)
async def update_event(
    record_id: uuid.UUID,
    payload: NonConformingEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).update_event(
        record_id, payload, _actor(current_user)
    )
    if not row:
        return ApiResponse(code=404, message="事件不存在")
    await db.commit()
    return ApiResponse(data=NonConformingEventResponse.model_validate(row))


@router.post(
    "/non-conforming-events/{record_id}/close",
    response_model=ProductionApiResponse[NonConformingEventResponse],
)
async def close_event(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).close_event(record_id, _actor(current_user))
    if not row:
        return ApiResponse(code=404, message="事件不存在")
    await db.commit()
    return ApiResponse(data=NonConformingEventResponse.model_validate(row))


@router.delete(
    "/non-conforming-events/{record_id}", response_model=ProductionApiResponse[None]
)
async def delete_event(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await OperationsService(db).delete(NonConformingEvent, record_id)
    if not deleted:
        return ApiResponse(code=404, message="事件不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get("/shift-logs", response_model=ProductionApiResponse[list[ShiftLogResponse]])
async def list_shift_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    workshop: str | None = None,
    shift: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    rows, total = await OperationsService(db).list_shift_logs(
        skip=(page - 1) * page_size, limit=page_size, workshop=workshop, shift=shift
    )
    return _page(rows, ShiftLogResponse, page, page_size, total)


@router.post("/shift-logs", response_model=ProductionApiResponse[ShiftLogResponse])
async def create_shift_log(
    payload: ShiftLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).create_shift_log(payload, _actor(current_user))
    await db.commit()
    return ApiResponse(data=ShiftLogResponse.model_validate(row))


@router.put(
    "/shift-logs/{record_id}", response_model=ProductionApiResponse[ShiftLogResponse]
)
async def update_shift_log(
    record_id: uuid.UUID,
    payload: ShiftLogUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).update_shift_log(
        record_id, payload, _actor(current_user)
    )
    if not row:
        return ApiResponse(code=404, message="班次日志不存在")
    await db.commit()
    return ApiResponse(data=ShiftLogResponse.model_validate(row))


@router.delete("/shift-logs/{record_id}", response_model=ProductionApiResponse[None])
async def delete_shift_log(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await OperationsService(db).delete(ShiftLog, record_id)
    if not deleted:
        return ApiResponse(code=404, message="班次日志不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get(
    "/shift-handovers",
    response_model=ProductionApiResponse[list[ShiftHandoverResponse]],
)
async def list_handovers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    workshop: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    rows, total = await OperationsService(db).list_handovers(
        skip=(page - 1) * page_size, limit=page_size, workshop=workshop, status=status
    )
    return _page(rows, ShiftHandoverResponse, page, page_size, total)


@router.post(
    "/shift-handovers", response_model=ProductionApiResponse[ShiftHandoverResponse]
)
async def create_handover(
    payload: ShiftHandoverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).create_handover(payload, _actor(current_user))
    await db.commit()
    return ApiResponse(data=ShiftHandoverResponse.model_validate(row))


@router.put(
    "/shift-handovers/{record_id}",
    response_model=ProductionApiResponse[ShiftHandoverResponse],
)
async def update_handover(
    record_id: uuid.UUID,
    payload: ShiftHandoverUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).update_handover(
        record_id, payload, _actor(current_user)
    )
    if not row:
        return ApiResponse(code=404, message="交接记录不存在")
    await db.commit()
    return ApiResponse(data=ShiftHandoverResponse.model_validate(row))


@router.post(
    "/shift-handovers/{record_id}/confirm",
    response_model=ProductionApiResponse[ShiftHandoverResponse],
)
async def confirm_handover(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    row = await OperationsService(db).confirm_handover(record_id, _actor(current_user))
    if not row:
        return ApiResponse(code=404, message="交接记录不存在")
    await db.commit()
    return ApiResponse(data=ShiftHandoverResponse.model_validate(row))


@router.delete(
    "/shift-handovers/{record_id}", response_model=ProductionApiResponse[None]
)
async def delete_handover(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await OperationsService(db).delete(ShiftHandover, record_id)
    if not deleted:
        return ApiResponse(code=404, message="交接记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")
