"""Safety API — 应急管理端点。

应急预案台账（含附件上传/下载）、演练计划/记录、应急物资台账与统计。
"""

from __future__ import annotations

import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.schemas.emergency_mgmt import (
    EmergencyDrillCreate,
    EmergencyDrillListResponse,
    EmergencyDrillResponse,
    EmergencyDrillUpdate,
    EmergencyMgmtStatsResponse,
    EmergencyPlanCreate,
    EmergencyPlanListResponse,
    EmergencyPlanResponse,
    EmergencyPlanUpdate,
    EmergencySupplyCreate,
    EmergencySupplyListResponse,
    EmergencySupplyResponse,
    EmergencySupplyUpdate,
)
from app.modules.safety.service.emergency_mgmt import EmergencyMgmtService
from app.shared.schemas import ApiResponseEnvelope

emergency_mgmt_router = APIRouter()

_PLAN_ALLOWED_EXTS = {".pdf", ".doc", ".docx"}
_PLAN_MAX_BYTES = 50 * 1024 * 1024


# ---------- 应急预案 ----------


@emergency_mgmt_router.get(
    "/emergency-plans",
    response_model=ApiResponseEnvelope[EmergencyPlanListResponse],
    summary="应急预案分页列表（类型/状态/关键字）",
)
async def list_emergency_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    plan_type: str | None = Query(
        None, description="类型: comprehensive/special/onsite"
    ),
    status: str | None = Query(None, description="状态: active/revising/obsolete"),
    keyword: str | None = Query(None, description="预案名称/部门关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanListResponse]:
    service = EmergencyMgmtService(db)
    items, total = await service.list_plans(
        page=page,
        page_size=page_size,
        plan_type=plan_type,
        status=status,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=EmergencyPlanListResponse(
            items=[EmergencyPlanResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@emergency_mgmt_router.get(
    "/emergency-plans/{plan_id}",
    response_model=ApiResponseEnvelope[EmergencyPlanResponse],
    summary="应急预案详情",
)
async def get_emergency_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanResponse]:
    service = EmergencyMgmtService(db)
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise NotFoundException("应急预案")
    return ApiResponseEnvelope(data=EmergencyPlanResponse.model_validate(plan))


@emergency_mgmt_router.post(
    "/emergency-plans",
    response_model=ApiResponseEnvelope[EmergencyPlanResponse],
    summary="新增应急预案",
)
async def create_emergency_plan(
    data: EmergencyPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    plan = await service.create_plan(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(plan)
    return ApiResponseEnvelope(data=EmergencyPlanResponse.model_validate(plan))


@emergency_mgmt_router.put(
    "/emergency-plans/{plan_id}",
    response_model=ApiResponseEnvelope[EmergencyPlanResponse],
    summary="更新应急预案",
)
async def update_emergency_plan(
    plan_id: UUID,
    data: EmergencyPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    plan = await service.update_plan(plan_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(plan)
    return ApiResponseEnvelope(data=EmergencyPlanResponse.model_validate(plan))


@emergency_mgmt_router.delete(
    "/emergency-plans/{plan_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除应急预案（软删除）",
)
async def delete_emergency_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    deleted = await service.delete_plan(plan_id)
    if not deleted:
        raise NotFoundException("应急预案")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@emergency_mgmt_router.post(
    "/emergency-plans/{plan_id}/file",
    response_model=ApiResponseEnvelope[EmergencyPlanResponse],
    summary="上传预案文件",
)
async def upload_emergency_plan_file(
    plan_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in _PLAN_ALLOWED_EXTS:
        raise AppException(status_code=422, message="预案文件仅支持 pdf/doc/docx")
    content = await file.read()
    if len(content) > _PLAN_MAX_BYTES:
        raise AppException(status_code=422, message="预案文件不能超过 50MB")

    upload_dir = os.path.join("uploads", "safety", "emergency")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"plan_{plan_id}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    service = EmergencyMgmtService(db)
    plan = await service.set_plan_file(
        plan_id, file_path, file.filename or "plan", user_id=current_user.id
    )
    await db.commit()
    await db.refresh(plan)
    return ApiResponseEnvelope(data=EmergencyPlanResponse.model_validate(plan))


@emergency_mgmt_router.get(
    "/emergency-plans/{plan_id}/file",
    response_model=None,
    summary="下载预案文件",
)
async def download_emergency_plan_file(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> FileResponse:
    service = EmergencyMgmtService(db)
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise NotFoundException("应急预案")
    if not plan.file_path or not os.path.exists(plan.file_path):
        raise NotFoundException("预案文件")
    return FileResponse(
        plan.file_path,
        filename=plan.file_name or "plan",
        media_type="application/octet-stream",
    )


# ---------- 应急演练 ----------


@emergency_mgmt_router.get(
    "/emergency-drills",
    response_model=ApiResponseEnvelope[EmergencyDrillListResponse],
    summary="应急演练分页列表（类型/状态/年度/关键字）",
)
async def list_emergency_drills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    drill_type: str | None = Query(
        None, description="类型: tabletop/practical/comprehensive"
    ),
    status: str | None = Query(None, description="状态: planned/done/cancelled"),
    year: int | None = Query(None, description="按实际/计划日期的年份"),
    keyword: str | None = Query(None, description="名称/情景/地点关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyDrillListResponse]:
    service = EmergencyMgmtService(db)
    items, total = await service.list_drills(
        page=page,
        page_size=page_size,
        drill_type=drill_type,
        status=status,
        year=year,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=EmergencyDrillListResponse(
            items=[EmergencyDrillResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@emergency_mgmt_router.get(
    "/emergency-drills/{drill_id}",
    response_model=ApiResponseEnvelope[EmergencyDrillResponse],
    summary="应急演练详情",
)
async def get_emergency_drill(
    drill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyDrillResponse]:
    service = EmergencyMgmtService(db)
    drill = await service.get_drill(drill_id)
    if drill is None:
        raise NotFoundException("应急演练")
    return ApiResponseEnvelope(data=EmergencyDrillResponse.model_validate(drill))


@emergency_mgmt_router.post(
    "/emergency-drills",
    response_model=ApiResponseEnvelope[EmergencyDrillResponse],
    summary="新增应急演练（计划或记录）",
)
async def create_emergency_drill(
    data: EmergencyDrillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyDrillResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    drill = await service.create_drill(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(drill)
    return ApiResponseEnvelope(data=EmergencyDrillResponse.model_validate(drill))


@emergency_mgmt_router.put(
    "/emergency-drills/{drill_id}",
    response_model=ApiResponseEnvelope[EmergencyDrillResponse],
    summary="更新应急演练",
)
async def update_emergency_drill(
    drill_id: UUID,
    data: EmergencyDrillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyDrillResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    drill = await service.update_drill(drill_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(drill)
    return ApiResponseEnvelope(data=EmergencyDrillResponse.model_validate(drill))


@emergency_mgmt_router.delete(
    "/emergency-drills/{drill_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除应急演练（软删除）",
)
async def delete_emergency_drill(
    drill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    deleted = await service.delete_drill(drill_id)
    if not deleted:
        raise NotFoundException("应急演练")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


# ---------- 应急物资 ----------


@emergency_mgmt_router.get(
    "/emergency-supplies",
    response_model=ApiResponseEnvelope[EmergencySupplyListResponse],
    summary="应急物资分页列表（类别/状态/部门/关键字）",
)
async def list_emergency_supplies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: str | None = Query(
        None,
        description="类别: firefighting/protective/medical/communication/"
        "leak_sealing/other",
    ),
    status: str | None = Query(None, description="状态: good/repair/scrapped"),
    department: str | None = Query(None, description="管理部门"),
    keyword: str | None = Query(None, description="物资名称/位置关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencySupplyListResponse]:
    service = EmergencyMgmtService(db)
    items, total = await service.list_supplies(
        page=page,
        page_size=page_size,
        category=category,
        status=status,
        department=department,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=EmergencySupplyListResponse(
            items=[EmergencySupplyResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@emergency_mgmt_router.get(
    "/emergency-supplies/{supply_id}",
    response_model=ApiResponseEnvelope[EmergencySupplyResponse],
    summary="应急物资详情",
)
async def get_emergency_supply(
    supply_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencySupplyResponse]:
    service = EmergencyMgmtService(db)
    supply = await service.get_supply(supply_id)
    if supply is None:
        raise NotFoundException("应急物资")
    return ApiResponseEnvelope(data=EmergencySupplyResponse.model_validate(supply))


@emergency_mgmt_router.post(
    "/emergency-supplies",
    response_model=ApiResponseEnvelope[EmergencySupplyResponse],
    summary="新增应急物资",
)
async def create_emergency_supply(
    data: EmergencySupplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencySupplyResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    supply = await service.create_supply(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(supply)
    return ApiResponseEnvelope(data=EmergencySupplyResponse.model_validate(supply))


@emergency_mgmt_router.put(
    "/emergency-supplies/{supply_id}",
    response_model=ApiResponseEnvelope[EmergencySupplyResponse],
    summary="更新应急物资",
)
async def update_emergency_supply(
    supply_id: UUID,
    data: EmergencySupplyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencySupplyResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    supply = await service.update_supply(supply_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(supply)
    return ApiResponseEnvelope(data=EmergencySupplyResponse.model_validate(supply))


@emergency_mgmt_router.delete(
    "/emergency-supplies/{supply_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除应急物资（软删除）",
)
async def delete_emergency_supply(
    supply_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = EmergencyMgmtService(db)
    deleted = await service.delete_supply(supply_id)
    if not deleted:
        raise NotFoundException("应急物资")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


# ---------- 汇总统计 ----------


@emergency_mgmt_router.get(
    "/emergency-mgmt/stats",
    response_model=ApiResponseEnvelope[EmergencyMgmtStatsResponse],
    summary="应急管理统计（预案/演练/物资汇总）",
)
async def get_emergency_mgmt_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyMgmtStatsResponse]:
    service = EmergencyMgmtService(db)
    return ApiResponseEnvelope(data=await service.get_stats())
