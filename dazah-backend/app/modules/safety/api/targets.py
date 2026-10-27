"""Safety API — 目标责任与绩效端点。

年度安全目标台账 + 考核期进度记录，支持按年份/类别/部门/状态检索，
统计接口输出各部门目标达成情况。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.schemas.targets import (
    SafetyTargetCreate,
    SafetyTargetListResponse,
    SafetyTargetRecordCreate,
    SafetyTargetRecordResponse,
    SafetyTargetRecordUpdate,
    SafetyTargetResponse,
    SafetyTargetStatsResponse,
    SafetyTargetUpdate,
)
from app.modules.safety.service.target import SafetyTargetService
from app.shared.schemas import ApiResponseEnvelope

safety_targets_router = APIRouter()


@safety_targets_router.get(
    "/safety-targets",
    response_model=ApiResponseEnvelope[SafetyTargetListResponse],
    summary="安全目标分页列表（年份/类别/部门/状态/关键字）",
)
async def list_safety_targets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    year: int | None = Query(None, description="目标年度"),
    category: str | None = Query(None, description="目标类别"),
    department: str | None = Query(None, description="责任部门"),
    status: str | None = Query(
        None, description="状态: in_progress/achieved/not_achieved"
    ),
    keyword: str | None = Query(None, description="目标名称/指标关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetListResponse]:
    service = SafetyTargetService(db)
    items, total = await service.list_targets(
        page=page,
        page_size=page_size,
        year=year,
        category=category,
        department=department,
        status=status,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=SafetyTargetListResponse(
            items=[SafetyTargetResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_targets_router.get(
    "/safety-targets/stats",
    response_model=ApiResponseEnvelope[SafetyTargetStatsResponse],
    summary="安全目标统计（部门达成情况）",
)
async def get_safety_target_stats(
    year: int | None = Query(None, description="目标年度"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetStatsResponse]:
    service = SafetyTargetService(db)
    return ApiResponseEnvelope(data=await service.get_stats(year=year))


@safety_targets_router.get(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="安全目标详情（含进度记录）",
)
async def get_safety_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    service = SafetyTargetService(db)
    target = await service.get_target(target_id)
    if target is None:
        raise NotFoundException("安全目标")
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.post(
    "/safety-targets",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="新增安全目标",
)
async def create_safety_target(
    data: SafetyTargetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    target = await service.create_target(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(target)
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.put(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[SafetyTargetResponse],
    summary="更新安全目标",
)
async def update_safety_target(
    target_id: UUID,
    data: SafetyTargetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    target = await service.update_target(target_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(target)
    return ApiResponseEnvelope(data=SafetyTargetResponse.model_validate(target))


@safety_targets_router.delete(
    "/safety-targets/{target_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除安全目标（软删除）",
)
async def delete_safety_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    deleted = await service.delete_target(target_id)
    if not deleted:
        raise NotFoundException("安全目标")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@safety_targets_router.put(
    "/safety-targets/{target_id}/records/{period}",
    response_model=ApiResponseEnvelope[SafetyTargetRecordResponse],
    summary="录入/更新目标进度（按考核期 upsert 语义：存在即更新）",
)
async def upsert_safety_target_record(
    target_id: UUID,
    period: str,
    data: SafetyTargetRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyTargetRecordResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    existing = await service.get_record(target_id, period)
    if existing is None:
        create_data = SafetyTargetRecordCreate(
            period=period,
            actual_value=data.actual_value or "",
            completion_pct=data.completion_pct,
            note=data.note or "",
        )
        record = await service.create_record(
            target_id, create_data, user_id=current_user.id
        )
    else:
        record = await service.update_record(
            target_id, period, data, user_id=current_user.id
        )
    await db.commit()
    await db.refresh(record)
    return ApiResponseEnvelope(data=SafetyTargetRecordResponse.model_validate(record))


@safety_targets_router.delete(
    "/safety-targets/{target_id}/records/{period}",
    response_model=ApiResponseEnvelope[None],
    summary="删除目标进度记录（软删除）",
)
async def delete_safety_target_record(
    target_id: UUID,
    period: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyTargetService(db)
    deleted = await service.delete_record(target_id, period)
    if not deleted:
        raise NotFoundException("进度记录")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
