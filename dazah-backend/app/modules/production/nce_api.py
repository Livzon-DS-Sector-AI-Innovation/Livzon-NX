"""非密事件与运行偏差 API."""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.nce_schemas import NCECreate, NCEResponse, NCEUpdate
from app.modules.production.nce_service import NCEService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


def get_nce_service(session: AsyncSession = Depends(get_db)) -> NCEService:
    return NCEService(session)


@router.get("/non-conforming-events", summary="非密事件列表")
async def list_nce(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(None),
    event_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    svc: NCEService = Depends(get_nce_service),
):
    items, total = await svc.list_records(
        page=page,
        page_size=page_size,
        workshop=workshop,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
    )
    return paginated_response(
        [NCEResponse.model_validate(i) for i in items], page, page_size, total
    )


@router.get(
    "/non-conforming-events/{event_id}/affected-batches",
    summary="查询非密事件关联的批次",
)
async def get_affected_batches(
    event_id: UUID, svc: NCEService = Depends(get_nce_service)
):
    batches = await svc.get_affected_batches(event_id)
    return success_response(batches)


@router.post("/non-conforming-events", summary="创建非密事件")
async def create_nce(data: NCECreate, svc: NCEService = Depends(get_nce_service)):
    record = await svc.create_record(data.model_dump())
    return success_response(NCEResponse.model_validate(record), message="创建成功")


@router.put("/non-conforming-events/{record_id}", summary="更新非密事件")
async def update_nce(
    record_id: UUID, data: NCEUpdate, svc: NCEService = Depends(get_nce_service)
):
    record = await svc.update_record(record_id, data.model_dump(exclude_unset=True))
    return success_response(NCEResponse.model_validate(record), message="更新成功")


@router.delete("/non-conforming-events/{record_id}", summary="删除非密事件")
async def delete_nce(record_id: UUID, svc: NCEService = Depends(get_nce_service)):
    await svc.delete_record(record_id)
    return success_response(None, message="删除成功")
