"""生产日志与交接班 API routes."""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.shift_log_schemas import (
    ShiftLogCreate,
    ShiftLogResponse,
    ShiftLogUpdate,
)
from app.modules.production.shift_log_service import ShiftLogService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


def get_shift_log_service(
    session: AsyncSession = Depends(get_db),
) -> ShiftLogService:
    return ShiftLogService(session)


# ═══════════════════════════════════════
# Shift Log CRUD
# ═══════════════════════════════════════


@router.get("/shift-logs", summary="生产日志列表")
async def list_shift_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(None, description="车间"),
    shift: str | None = Query(None, description="班次"),
    date_from: str | None = Query(None, description="开始日期"),
    date_to: str | None = Query(None, description="结束日期"),
    svc: ShiftLogService = Depends(get_shift_log_service),
):
    items, total = await svc.list_records(
        page=page,
        page_size=page_size,
        workshop=workshop,
        shift=shift,
        date_from=date_from,
        date_to=date_to,
    )
    response_items = [ShiftLogResponse.model_validate(item) for item in items]
    return paginated_response(response_items, page, page_size, total)


@router.get("/shift-logs/{record_id}", summary="生产日志详情")
async def get_shift_log(
    record_id: UUID,
    svc: ShiftLogService = Depends(get_shift_log_service),
):
    record = await svc.get_record(record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    return success_response(ShiftLogResponse.model_validate(record))


@router.post("/shift-logs", summary="创建生产日志")
async def create_shift_log(
    data: ShiftLogCreate,
    svc: ShiftLogService = Depends(get_shift_log_service),
):
    record = await svc.create_record(data.model_dump())
    return success_response(ShiftLogResponse.model_validate(record), message="创建成功")


@router.put("/shift-logs/{record_id}", summary="更新生产日志")
async def update_shift_log(
    record_id: UUID,
    data: ShiftLogUpdate,
    svc: ShiftLogService = Depends(get_shift_log_service),
):
    record = await svc.update_record(record_id, data.model_dump(exclude_unset=True))
    return success_response(ShiftLogResponse.model_validate(record), message="更新成功")


@router.delete("/shift-logs/{record_id}", summary="删除生产日志")
async def delete_shift_log(
    record_id: UUID,
    svc: ShiftLogService = Depends(get_shift_log_service),
):
    await svc.delete_record(record_id)
    return success_response(None, message="删除成功")
