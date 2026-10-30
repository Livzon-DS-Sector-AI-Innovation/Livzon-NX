"""Safety API — 危化品与 MSDS 端点。

危化品档案（含 MSDS 多附件上传/下载/在线预览/AI 识别）与车间存量台账
（超储预警，本地口径；页面展示走飞书统计表镜像）。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.core.upload_security import read_upload_secure, sniff_upload_mime
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    ChemicalInventoryListResponse,
    ChemicalInventoryResponse,
    ChemicalInventoryUpdate,
    ChemicalMsdsFileItem,
    ChemicalMsdsFileListResponse,
    ChemicalMsdsUploadResponse,
    HazardousChemicalCreate,
    HazardousChemicalListResponse,
    HazardousChemicalResponse,
    HazardousChemicalUpdate,
    HazchemStatsResponse,
)
from app.modules.safety.service.hazchem import (
    MSDS_ALLOWED_EXTS,
    MSDS_MAX_BYTES,
    HazchemService,
    build_msds_storage_key,
    read_msds_object,
    store_msds_object,
)
from app.modules.safety.service.msds_extract import extract_msds_suggestion
from app.platform.storage.preview import resolve_preview_content
from app.shared.schemas import ApiResponseEnvelope

hazchem_router = APIRouter()


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


@hazchem_router.get(
    "/hazardous-chemicals/{chemical_id}/msds-files",
    response_model=ApiResponseEnvelope[ChemicalMsdsFileListResponse],
    summary="MSDS 附件列表",
)
async def list_msds_files(
    chemical_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalMsdsFileListResponse]:
    service = HazchemService(db)
    items = await service.list_msds_files(chemical_id)
    return ApiResponseEnvelope(
        data=ChemicalMsdsFileListResponse(
            items=[ChemicalMsdsFileItem.model_validate(item) for item in items]
        )
    )


@hazchem_router.post(
    "/hazardous-chemicals/{chemical_id}/msds-files",
    response_model=ApiResponseEnvelope[ChemicalMsdsUploadResponse],
    summary="上传 MSDS 附件（附带 AI 识别档案字段建议）",
)
async def upload_msds_file(
    chemical_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalMsdsUploadResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    file_name, content = await read_upload_secure(
        file,
        max_bytes=MSDS_MAX_BYTES,
        allowed_extensions=MSDS_ALLOWED_EXTS,
        what="MSDS 文件",
    )
    file_ext = Path(file_name).suffix.lower()
    if file_ext not in MSDS_ALLOWED_EXTS:
        raise AppException(
            status_code=422,
            message="MSDS 仅支持 pdf/doc/docx/png/jpg 文件",
        )

    service = HazchemService(db)
    chemical = await service.get_chemical(chemical_id)
    if chemical is None:
        raise NotFoundException("危化品档案")
    # 记录魔数嗅探出的真实类型，不信任客户端 Content-Type 头
    content_type = sniff_upload_mime(file_name, content)
    storage_key = store_msds_object(
        build_msds_storage_key(chemical_id, file_ext), content, content_type
    )
    attachment = await service.add_msds_file(
        chemical_id,
        file_name=file_name,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(content),
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(attachment)
    await db.refresh(chemical)

    suggestion, ai_error = await extract_msds_suggestion(
        file_name=file_name, content=content
    )
    return ApiResponseEnvelope(
        data=ChemicalMsdsUploadResponse(
            file=ChemicalMsdsFileItem.model_validate(attachment),
            chemical=HazardousChemicalResponse.model_validate(chemical),
            ai_suggestion=suggestion,
            ai_error=ai_error,
        )
    )


@hazchem_router.get(
    "/hazardous-chemicals/{chemical_id}/msds-files/{file_id}/content",
    response_model=None,
    summary="下载 MSDS 附件",
)
async def download_msds_file(
    chemical_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    service = HazchemService(db)
    attachment = await service.get_msds_file(chemical_id, file_id)
    stored = read_msds_object(attachment.storage_key)
    if stored is None:
        raise NotFoundException("MSDS 文件")
    data, content_type = stored
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(attachment.file_name)}"
            )
        },
    )


@hazchem_router.get(
    "/hazardous-chemicals/{chemical_id}/msds-files/{file_id}/preview",
    response_model=None,
    summary="MSDS 附件在线预览（office 转 PDF）",
)
async def preview_msds_file(
    chemical_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    service = HazchemService(db)
    attachment = await service.get_msds_file(chemical_id, file_id)
    stored = read_msds_object(attachment.storage_key)
    if stored is None:
        raise NotFoundException("MSDS 文件")
    data, _content_type = stored
    try:
        preview_data, preview_type, preview_name = resolve_preview_content(
            data, attachment.file_name
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=415) from exc
    return Response(
        content=preview_data,
        media_type=preview_type,
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{quote(preview_name)}"
            )
        },
    )


@hazchem_router.post(
    "/hazardous-chemicals/{chemical_id}/msds-files/{file_id}/extract",
    response_model=ApiResponseEnvelope[ChemicalMsdsUploadResponse],
    summary="重新 AI 识别 MSDS 附件内容（返回档案字段建议）",
)
async def extract_msds_file(
    chemical_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChemicalMsdsUploadResponse]:
    service = HazchemService(db)
    attachment = await service.get_msds_file(chemical_id, file_id)
    chemical = await service.get_chemical(chemical_id)
    if chemical is None:
        raise NotFoundException("危化品档案")
    stored = read_msds_object(attachment.storage_key)
    if stored is None:
        raise NotFoundException("MSDS 文件")
    suggestion, ai_error = await extract_msds_suggestion(
        file_name=attachment.file_name, content=stored[0]
    )
    return ApiResponseEnvelope(
        data=ChemicalMsdsUploadResponse(
            file=ChemicalMsdsFileItem.model_validate(attachment),
            chemical=HazardousChemicalResponse.model_validate(chemical),
            ai_suggestion=suggestion,
            ai_error=ai_error,
        )
    )


@hazchem_router.delete(
    "/hazardous-chemicals/{chemical_id}/msds-files/{file_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除 MSDS 附件（软删除）",
)
async def delete_msds_file(
    chemical_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = HazchemService(db)
    await service.delete_msds_file(chemical_id, file_id)
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


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
