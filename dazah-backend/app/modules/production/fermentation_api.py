"""Fermentation record API routes."""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.fermentation_schemas import (
    FermentationCreate,
    FermentationResponse,
    FermentationStatusUpdate,
    FermentationUpdate,
)
from app.modules.production.fermentation_service import FermentationService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


def get_fermentation_service(
    session: AsyncSession = Depends(get_db),
) -> FermentationService:
    return FermentationService(session)


# ═══════════════════════════════════════
# Fermentation Records CRUD
# ═══════════════════════════════════════


@router.get("/fermentation", summary="发酵记录列表")
async def list_fermentation_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_name: str | None = Query(None, description="产品名称"),
    batch_no: str | None = Query(None, description="批号搜索"),
    status: str | None = Query(None, description="状态"),
    fermenter: str | None = Query(None, description="发酵罐搜索"),
    svc: FermentationService = Depends(get_fermentation_service),
):
    items, total = await svc.list_records(
        page=page,
        page_size=page_size,
        product_name=product_name,
        batch_no=batch_no,
        status=status,
        fermenter=fermenter,
    )
    response_items = [FermentationResponse.model_validate(item) for item in items]
    return paginated_response(response_items, page, page_size, total)


@router.get(
    "/fermentation/{record_id}/related-events", summary="查询批次相关的非密事件"
)
async def get_related_events(record_id: UUID, session: AsyncSession = Depends(get_db)):
    from sqlalchemy import text

    rows = await session.execute(
        text("""
        SELECT e.id, e.event_time, e.restore_time, e.impact_duration, e.event_type,
        e.workshop, e.description, e.impact_scope, e.action_taken
        FROM production.nce_batch_links l
        JOIN production.non_conforming_events e ON e.id = l.nce_id
        WHERE l.batch_id = :bid AND e.is_deleted = false
        ORDER BY e.event_time DESC
    """),
        {"bid": record_id},
    )
    events = [
        {
            "id": str(r[0]),
            "event_time": r[1],
            "restore_time": r[2],
            "impact_duration": r[3],
            "event_type": r[4],
            "workshop": r[5],
            "description": r[6],
            "impact_scope": r[7],
            "action_taken": r[8],
        }
        for r in rows
    ]
    return success_response(events)


@router.get("/fermentation/{record_id}", summary="发酵记录详情")
async def get_fermentation_record(
    record_id: UUID,
    svc: FermentationService = Depends(get_fermentation_service),
):
    record = await svc.get_record(record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    return success_response(FermentationResponse.model_validate(record))


@router.post("/fermentation", summary="创建发酵记录")
async def create_fermentation_record(
    data: FermentationCreate,
    svc: FermentationService = Depends(get_fermentation_service),
):
    record = await svc.create_record(data.model_dump())
    return success_response(
        FermentationResponse.model_validate(record), message="创建成功"
    )


@router.put("/fermentation/{record_id}", summary="更新发酵记录")
async def update_fermentation_record(
    record_id: UUID,
    data: FermentationUpdate,
    svc: FermentationService = Depends(get_fermentation_service),
):
    record = await svc.update_record(record_id, data.model_dump(exclude_unset=True))
    return success_response(
        FermentationResponse.model_validate(record), message="更新成功"
    )


@router.put("/fermentation/{record_id}/status", summary="更新发酵状态")
async def update_fermentation_status(
    record_id: UUID,
    data: FermentationStatusUpdate,
    svc: FermentationService = Depends(get_fermentation_service),
):
    record = await svc.update_status(record_id, data.status)
    return success_response(
        FermentationResponse.model_validate(record), message="状态更新成功"
    )


@router.delete("/fermentation/{record_id}", summary="删除发酵记录")
async def delete_fermentation_record(
    record_id: UUID,
    svc: FermentationService = Depends(get_fermentation_service),
):
    await svc.delete_record(record_id)
    return success_response(None, message="删除成功")
