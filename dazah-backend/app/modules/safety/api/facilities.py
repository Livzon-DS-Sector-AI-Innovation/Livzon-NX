"""Safety API — 安全设施台账端点。

洗眼器/气体检测仪/防护设施等安全设备设施的台账维护、类别检查卡
获取与点检记录提交。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.schemas.facilities import (
    CreateSafetyFacilityInspectionRequest,
    SafetyFacilityChecklistResponse,
    SafetyFacilityCreate,
    SafetyFacilityInspectionListResponse,
    SafetyFacilityInspectionResponse,
    SafetyFacilityListResponse,
    SafetyFacilityResponse,
    SafetyFacilityStatsResponse,
    SafetyFacilityUpdate,
)
from app.modules.safety.service.facility import (
    SafetyFacilityService,
    get_checklist,
)
from app.shared.schemas import ApiResponseEnvelope

safety_facilities_router = APIRouter()


@safety_facilities_router.get(
    "/safety-facilities",
    response_model=ApiResponseEnvelope[SafetyFacilityListResponse],
    summary="安全设施分页列表（类别/部门/状态/到期/关键字）",
)
async def list_safety_facilities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: str | None = Query(
        None, description="类别: eyewash/gas_detector/protective/other"
    ),
    department: str | None = Query(None, description="所属部门/车间"),
    status: str | None = Query(None, description="状态: normal/damaged/scrapped"),
    expiry_status: str | None = Query(
        None, description="到期筛选: expiring(90天内)/expired"
    ),
    keyword: str | None = Query(None, description="名称/编号/位置关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityListResponse]:
    service = SafetyFacilityService(db)
    items, total = await service.list_facilities(
        page=page,
        page_size=page_size,
        category=category,
        department=department,
        status=status,
        expiry_status=expiry_status,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=SafetyFacilityListResponse(
            items=[SafetyFacilityResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_facilities_router.get(
    "/safety-facilities/stats",
    response_model=ApiResponseEnvelope[SafetyFacilityStatsResponse],
    summary="安全设施统计（类别/状态/到期/异常）",
)
async def get_safety_facility_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityStatsResponse]:
    service = SafetyFacilityService(db)
    return ApiResponseEnvelope(data=await service.get_stats())


@safety_facilities_router.get(
    "/safety-facilities/checklist",
    response_model=ApiResponseEnvelope[SafetyFacilityChecklistResponse],
    summary="按类别获取点检卡项",
)
async def get_safety_facility_checklist(
    category: str = Query(
        ..., description="类别: eyewash/gas_detector/protective/other"
    ),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityChecklistResponse]:
    return ApiResponseEnvelope(data=get_checklist(category))


@safety_facilities_router.get(
    "/safety-facilities/{facility_id}",
    response_model=ApiResponseEnvelope[SafetyFacilityResponse],
    summary="安全设施详情",
)
async def get_safety_facility(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityResponse]:
    service = SafetyFacilityService(db)
    facility = await service.get_facility(facility_id)
    if facility is None:
        raise NotFoundException("安全设施")
    return ApiResponseEnvelope(data=SafetyFacilityResponse.model_validate(facility))


@safety_facilities_router.post(
    "/safety-facilities",
    response_model=ApiResponseEnvelope[SafetyFacilityResponse],
    summary="新增安全设施",
)
async def create_safety_facility(
    data: SafetyFacilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyFacilityService(db)
    facility = await service.create_facility(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(facility)
    return ApiResponseEnvelope(data=SafetyFacilityResponse.model_validate(facility))


@safety_facilities_router.put(
    "/safety-facilities/{facility_id}",
    response_model=ApiResponseEnvelope[SafetyFacilityResponse],
    summary="更新安全设施",
)
async def update_safety_facility(
    facility_id: UUID,
    data: SafetyFacilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyFacilityService(db)
    facility = await service.update_facility(facility_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(facility)
    return ApiResponseEnvelope(data=SafetyFacilityResponse.model_validate(facility))


@safety_facilities_router.delete(
    "/safety-facilities/{facility_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除安全设施（软删除）",
)
async def delete_safety_facility(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyFacilityService(db)
    deleted = await service.delete_facility(facility_id)
    if not deleted:
        raise NotFoundException("安全设施")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@safety_facilities_router.post(
    "/safety-facilities/{facility_id}/inspections",
    response_model=ApiResponseEnvelope[SafetyFacilityInspectionResponse],
    summary="提交安全设施点检",
)
async def create_safety_facility_inspection(
    facility_id: UUID,
    data: CreateSafetyFacilityInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityInspectionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = SafetyFacilityService(db)
    record = await service.create_inspection(
        facility_id, data, inspector_id=current_user.id
    )
    await db.commit()
    await db.refresh(record)
    return ApiResponseEnvelope(
        data=SafetyFacilityInspectionResponse.model_validate(record)
    )


@safety_facilities_router.get(
    "/safety-facility-inspections",
    response_model=ApiResponseEnvelope[SafetyFacilityInspectionListResponse],
    summary="安全设施点检记录分页",
)
async def list_safety_facility_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    facility_id: UUID | None = Query(None, description="按设施筛选"),
    result: str | None = Query(None, description="结论: pass/fail"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityInspectionListResponse]:
    service = SafetyFacilityService(db)
    items, total = await service.list_inspections(
        page=page,
        page_size=page_size,
        facility_id=facility_id,
        result=result,
    )
    return ApiResponseEnvelope(
        data=SafetyFacilityInspectionListResponse(
            items=[
                SafetyFacilityInspectionResponse.model_validate(item) for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@safety_facilities_router.get(
    "/safety-facilities/{facility_id}/inspections",
    response_model=ApiResponseEnvelope[SafetyFacilityInspectionListResponse],
    summary="单个设施的点检记录",
)
async def list_facility_inspections(
    facility_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SafetyFacilityInspectionListResponse]:
    service = SafetyFacilityService(db)
    facility = await service.get_facility(facility_id)
    if facility is None:
        raise NotFoundException("安全设施")
    items, total = await service.list_inspections(
        page=page, page_size=page_size, facility_id=facility_id
    )
    return ApiResponseEnvelope(
        data=SafetyFacilityInspectionListResponse(
            items=[
                SafetyFacilityInspectionResponse.model_validate(item) for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
