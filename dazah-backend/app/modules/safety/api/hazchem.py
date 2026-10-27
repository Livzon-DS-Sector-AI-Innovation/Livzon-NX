"""Safety API — 危化品与 MSDS 端点。

危化品档案（含 MSDS 文件上传/下载）与车间存量台账（超储预警）。
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
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    ChemicalInventoryListResponse,
    ChemicalInventoryResponse,
    ChemicalInventoryUpdate,
    HazardousChemicalCreate,
    HazardousChemicalListResponse,
    HazardousChemicalResponse,
    HazardousChemicalUpdate,
    HazchemStatsResponse,
)
from app.modules.safety.service.hazchem import HazchemService
from app.shared.schemas import ApiResponseEnvelope

hazchem_router = APIRouter()

_MSDS_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
_MSDS_MAX_BYTES = 30 * 1024 * 1024


@hazchem_router.get(
    "/hazardous-chemicals",
    response_model=ApiResponseEnvelope[HazardousChemicalListResponse],
    summary="危化品档案分页列表（类别/关键字）",
)
async def list_hazardous_chemicals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: str | None = Query(None, description="危险性类别"),
    keyword: str | None = Query(None, description="名称/别名/CAS 关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazardousChemicalListResponse]:
    service = HazchemService(db)
    items, total = await service.list_chemicals(
        page=page, page_size=page_size, category=category, keyword=keyword
    )
    return ApiResponseEnvelope(
        data=HazardousChemicalListResponse(
            items=[HazardousChemicalResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@hazchem_router.get(
    "/hazardous-chemicals/stats",
    response_model=ApiResponseEnvelope[HazchemStatsResponse],
    summary="危化品与存量统计（超储计数）",
)
async def get_hazchem_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazchemStatsResponse]:
    service = HazchemService(db)
    return ApiResponseEnvelope(data=await service.get_stats())


@hazchem_router.get(
    "/hazardous-chemicals/over-limit",
    response_model=ApiResponseEnvelope[list[ChemicalInventoryResponse]],
    summary="超储物料 Top（驾驶舱超储卡片数据源）",
)
async def get_over_limit_chemicals(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[ChemicalInventoryResponse]]:
    service = HazchemService(db)
    return ApiResponseEnvelope(data=await service.get_over_limit_top(limit=limit))


@hazchem_router.get(
    "/hazardous-chemicals/{chemical_id}",
    response_model=ApiResponseEnvelope[HazardousChemicalResponse],
    summary="危化品档案详情",
)
async def get_hazardous_chemical(
    chemical_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazardousChemicalResponse]:
    service = HazchemService(db)
    chemical = await service.get_chemical(chemical_id)
    if chemical is None:
        raise NotFoundException("危化品档案")
    return ApiResponseEnvelope(data=HazardousChemicalResponse.model_validate(chemical))


@hazchem_router.post(
    "/hazardous-chemicals",
    response_model=ApiResponseEnvelope[HazardousChemicalResponse],
    summary="新增危化品档案",
)
async def create_hazardous_chemical(
    data: HazardousChemicalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazardousChemicalResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    chemical = await service.create_chemical(data, user_id=current_user.id)
    await db.commit()
    await db.refresh(chemical)
    return ApiResponseEnvelope(data=HazardousChemicalResponse.model_validate(chemical))


@hazchem_router.put(
    "/hazardous-chemicals/{chemical_id}",
    response_model=ApiResponseEnvelope[HazardousChemicalResponse],
    summary="更新危化品档案",
)
async def update_hazardous_chemical(
    chemical_id: UUID,
    data: HazardousChemicalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazardousChemicalResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    chemical = await service.update_chemical(chemical_id, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(chemical)
    return ApiResponseEnvelope(data=HazardousChemicalResponse.model_validate(chemical))


@hazchem_router.delete(
    "/hazardous-chemicals/{chemical_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除危化品档案（软删除）",
)
async def delete_hazardous_chemical(
    chemical_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    deleted = await service.delete_chemical(chemical_id)
    if not deleted:
        raise NotFoundException("危化品档案")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@hazchem_router.post(
    "/hazardous-chemicals/{chemical_id}/msds",
    response_model=ApiResponseEnvelope[HazardousChemicalResponse],
    summary="上传 MSDS 文件",
)
async def upload_msds(
    chemical_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[HazardousChemicalResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in _MSDS_ALLOWED_EXTS:
        raise AppException(
            status_code=422,
            message="MSDS 仅支持 pdf/doc/docx/png/jpg 文件",
        )
    content = await file.read()
    if len(content) > _MSDS_MAX_BYTES:
        raise AppException(status_code=422, message="MSDS 文件不能超过 30MB")

    upload_dir = os.path.join("uploads", "safety", "hazchem")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"msds_{chemical_id}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    service = HazchemService(db)
    chemical = await service.set_msds_file(
        chemical_id, file_path, file.filename or "msds", user_id=current_user.id
    )
    await db.commit()
    await db.refresh(chemical)
    return ApiResponseEnvelope(data=HazardousChemicalResponse.model_validate(chemical))


@hazchem_router.get(
    "/hazardous-chemicals/{chemical_id}/msds",
    response_model=None,
    summary="下载 MSDS 文件",
)
async def download_msds(
    chemical_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> FileResponse:
    service = HazchemService(db)
    chemical = await service.get_chemical(chemical_id)
    if chemical is None:
        raise NotFoundException("危化品档案")
    if not chemical.msds_file_path or not os.path.exists(chemical.msds_file_path):
        raise NotFoundException("MSDS 文件")
    return FileResponse(
        chemical.msds_file_path,
        filename=chemical.msds_file_name or "msds",
        media_type="application/octet-stream",
    )


@hazchem_router.get(
    "/chemical-inventories",
    response_model=ApiResponseEnvelope[ChemicalInventoryListResponse],
    summary="危化品车间存量分页（可只看超储）",
)
async def list_chemical_inventories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(None, description="车间/库房"),
    chemical_id: UUID | None = Query(None, description="按化学品筛选"),
    over_limit_only: bool = Query(False, description="只看超储记录"),
    keyword: str | None = Query(None, description="化学品名/车间关键字"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalInventoryListResponse]:
    service = HazchemService(db)
    items, total = await service.list_inventories(
        page=page,
        page_size=page_size,
        workshop=workshop,
        chemical_id=chemical_id,
        over_limit_only=over_limit_only,
        keyword=keyword,
    )
    return ApiResponseEnvelope(
        data=ChemicalInventoryListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@hazchem_router.post(
    "/chemical-inventories",
    response_model=ApiResponseEnvelope[ChemicalInventoryResponse],
    summary="新增车间存量记录",
)
async def create_chemical_inventory(
    data: ChemicalInventoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalInventoryResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    inventory = await service.create_inventory(data, user_id=current_user.id)
    await db.commit()
    return ApiResponseEnvelope(data=await service.get_inventory_response(inventory.id))


@hazchem_router.put(
    "/chemical-inventories/{inventory_id}",
    response_model=ApiResponseEnvelope[ChemicalInventoryResponse],
    summary="更新车间存量",
)
async def update_chemical_inventory(
    inventory_id: UUID,
    data: ChemicalInventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalInventoryResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    inventory = await service.update_inventory(
        inventory_id, data, user_id=current_user.id
    )
    await db.commit()
    return ApiResponseEnvelope(data=await service.get_inventory_response(inventory.id))


@hazchem_router.delete(
    "/chemical-inventories/{inventory_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除车间存量记录（软删除）",
)
async def delete_chemical_inventory(
    inventory_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    deleted = await service.delete_inventory(inventory_id)
    if not deleted:
        raise NotFoundException("存量记录")
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
