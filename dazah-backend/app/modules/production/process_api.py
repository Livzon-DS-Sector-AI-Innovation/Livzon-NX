"""生产工序执行、进度和批次全貌 API。"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.production.process_catalog import PROCESS_STEPS
from app.modules.production.process_schemas import (
    BatchProfileResponse,
    BatchProgressResponse,
    ProcessDefinition,
    ProcessExecutionRecordCreate,
    ProcessExecutionRecordResponse,
    ProcessExecutionRecordUpdate,
)
from app.modules.production.process_service import ProcessExecutionService
from app.modules.production.schemas import ProductionApiResponse

router = APIRouter()


@router.get(
    "/process-catalog",
    response_model=ProductionApiResponse[list[ProcessDefinition]],
    summary="获取 203 车间工序与字段目录",
)
async def get_process_catalog(
    current_user: CurrentUser | None = Depends(get_current_user),
):
    return ApiResponse(
        data=[ProcessDefinition.model_validate(step) for step in PROCESS_STEPS]
    )


@router.get(
    "/process-records",
    response_model=ProductionApiResponse[list[ProcessExecutionRecordResponse]],
    summary="获取生产工序执行记录",
)
async def list_process_execution_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = None,
    workshop_code: str | None = None,
    process_code: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    records, total = await ProcessExecutionService(db).list_records(
        skip=(page - 1) * page_size,
        limit=page_size,
        batch_no=batch_no,
        workshop_code=workshop_code,
        process_code=process_code,
        status=status,
    )
    return ApiResponse(
        data=[
            ProcessExecutionRecordResponse.model_validate(record) for record in records
        ],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.post(
    "/process-records",
    response_model=ProductionApiResponse[ProcessExecutionRecordResponse],
    summary="创建生产工序执行记录",
)
async def create_process_execution_record(
    data: ProcessExecutionRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    actor_id = current_user.id if current_user else None
    record = await ProcessExecutionService(db).create_record(data, actor_id)
    await db.commit()
    return ApiResponse(data=ProcessExecutionRecordResponse.model_validate(record))


@router.put(
    "/process-records/{record_id}",
    response_model=ProductionApiResponse[ProcessExecutionRecordResponse],
    summary="更新生产工序执行记录",
)
async def update_process_execution_record(
    record_id: uuid.UUID,
    data: ProcessExecutionRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    actor_id = current_user.id if current_user else None
    record = await ProcessExecutionService(db).update_record(record_id, data, actor_id)
    if not record:
        return ApiResponse(code=404, message="工序执行记录不存在")
    await db.commit()
    return ApiResponse(data=ProcessExecutionRecordResponse.model_validate(record))


@router.post(
    "/process-records/{record_id}/complete",
    response_model=ProductionApiResponse[ProcessExecutionRecordResponse],
    summary="完成生产工序执行记录",
)
async def complete_process_execution_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    actor_id = current_user.id if current_user else None
    record = await ProcessExecutionService(db).complete_record(record_id, actor_id)
    if not record:
        return ApiResponse(code=404, message="工序执行记录不存在")
    await db.commit()
    return ApiResponse(data=ProcessExecutionRecordResponse.model_validate(record))


@router.delete(
    "/process-records/{record_id}",
    response_model=ProductionApiResponse[None],
    summary="删除生产工序执行记录",
)
async def delete_process_execution_record(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    deleted = await ProcessExecutionService(db).delete_record(record_id)
    if not deleted:
        return ApiResponse(code=404, message="工序执行记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@router.get(
    "/batch-progress",
    response_model=ProductionApiResponse[BatchProgressResponse],
    summary="获取批次工序进度总览",
)
async def get_batch_progress(
    workshop_code: str = Query("203", max_length=32),
    batch_no: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    progress = await ProcessExecutionService(db).get_progress(workshop_code, batch_no)
    return ApiResponse(data=progress)


@router.get(
    "/batch-profile/{batch_no}",
    response_model=ProductionApiResponse[BatchProfileResponse],
    summary="获取批次全貌",
)
async def get_batch_profile(
    batch_no: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    profile = await ProcessExecutionService(db).get_batch_profile(batch_no)
    return ApiResponse(data=profile)
