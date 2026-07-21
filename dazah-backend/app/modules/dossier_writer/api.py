"""Dossier Writer API endpoints."""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from app.core.database import get_db
from app.core.response import success_response, error_response
from .schemas import (
    ProductDossierCreate, ProductDossierUpdate,
    ProductDossierResponse, ProductDossierListResponse,
    ChapterResponse, ChapterDetailResponse,
    AssetResponse, AssetUploadResponse,
    ParseResultResponse, ExportRequest, ExportResponse,
)
from .service import DossierService
from .models import DossierChapter, ProductDossier, ChapterAsset
from .field_models import FieldMapping, FieldFillResult

router = APIRouter()


# ====== Product Dossier ======

@router.post("/products", response_model=dict)
async def create_product_dossier(
    data: ProductDossierCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建品种资料"""
    service = DossierService(db)
    try:
        dossier = await service.create_product_dossier(data)
        return success_response(
            data=ProductDossierResponse.model_validate(dossier),
            message="创建成功"
        )
    except ValueError as e:
        return error_response(message=str(e), status_code=400)


@router.get("/products", response_model=dict)
async def list_product_dossiers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取品种资料列表"""
    service = DossierService(db)
    items, total = await service.list_product_dossiers(skip, limit)
    return success_response(
        data={
            "items": [ProductDossierListResponse.model_validate(i) for i in items],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
        message="获取成功"
    )


@router.get("/products/{dossier_id}", response_model=dict)
async def get_product_dossier(
    dossier_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取品种资料详情"""
    service = DossierService(db)
    dossier = await service.get_product_dossier(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    return success_response(
        data=ProductDossierResponse.model_validate(dossier),
        message="获取成功"
    )


@router.put("/products/{dossier_id}", response_model=dict)
async def update_product_dossier(
    dossier_id: UUID,
    data: ProductDossierUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新品种资料"""
    service = DossierService(db)
    dossier = await service.update_product_dossier(dossier_id, data)
    if not dossier:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    return success_response(
        data=ProductDossierResponse.model_validate(dossier),
        message="更新成功"
    )


@router.delete("/products/{dossier_id}", response_model=dict)
async def delete_product_dossier(
    dossier_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除品种资料"""
    service = DossierService(db)
    success = await service.delete_product_dossier(dossier_id)
    if not success:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    return success_response(message="删除成功")


# ====== Template Upload ======

@router.post("/products/{dossier_id}/templates", response_model=dict)
async def upload_templates(
    dossier_id: UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """批量上传模板文件"""
    service = DossierService(db)
    
    results = []
    for file in files:
        # 验证文件类型
        if not file.filename or not file.filename.lower().endswith('.docx'):
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": "仅支持 .docx 格式文件"
            })
            continue
        
        try:
            # 读取文件内容
            content = await file.read()
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"[Upload] Processing file: {file.filename}, size: {len(content)} bytes")
            
            # 保存模板
            template = await service.save_template_file(dossier_id, file.filename, content)
            _logger.info(f"[Upload] Saved template: {template.id}, filename: {template.original_filename}")
            
            results.append({
                "file_id": str(template.id),
                "filename": template.original_filename,
                "file_path": template.file_path,
                "file_size": template.file_size,
                "status": "success"
            })
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"[Upload] Failed to save {file.filename}: {e}", exc_info=True)
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
    
    # 更新品种状态为 template_uploaded
    await service.repo.update_product_dossier(dossier_id, parse_status="template_uploaded")
    await service.db.commit()
    
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count
    
    # 自动触发匹配
    match_result = await service.match_assets_to_chapters(dossier_id)
    
    return success_response(
        data={
            "results": results,
            "success_count": success_count,
            "failed_count": failed_count,
            "matched_count": match_result.get("matched_count", 0),
            "unmatched_files": match_result.get("unmatched_files", []),
        },
        message=f"上传完成：成功 {success_count} 个，匹配 {match_result.get('matched_count', 0)} 个"
    )


# ====== Template Parsing ======

@router.post("/products/{dossier_id}/parse", response_model=dict)
async def parse_templates(
    dossier_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """解析模板生成章节树"""
    service = DossierService(db)
    result = await service.parse_templates(dossier_id)
    
    if result["success"]:
        return success_response(data=result, message=result["message"])
    else:
        return error_response(message=result["message"], detail=result.get("error"))


# ====== Chapter ======

@router.get("/products/{dossier_id}/chapters", response_model=dict)
async def get_chapter_tree(
    dossier_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节树"""
    service = DossierService(db)
    chapters = await service.get_chapter_tree(dossier_id)
    return success_response(data=chapters, message="获取成功")


@router.get("/chapters/{chapter_id}", response_model=dict)
async def get_chapter_detail(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节详情"""
    service = DossierService(db)
    chapter = await service.get_chapter_detail(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    return success_response(data=chapter, message="获取成功")


# ====== Asset ======

@router.post("/chapters/{chapter_id}/assets", response_model=dict)
async def upload_asset(
    chapter_id: UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """批量上传章节素材"""
    service = DossierService(db)
    
    results = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        asset = await service.upload_chapter_asset(chapter_id, file.filename, content)
        results.append(AssetUploadResponse(
            id=asset.id,
            original_filename=asset.original_filename,
            file_path=asset.file_path,
            file_type=asset.file_type,
            file_size=asset.file_size,
            uploaded_at=asset.uploaded_at,
            category_id=asset.category_id,
        ))
    
    return success_response(
        data={"assets": [r.model_dump(mode="json") for r in results], "count": len(results)},
        message=f"成功上传 {len(results)} 个素材"
    )


@router.get("/chapters/{chapter_id}/assets", response_model=dict)
async def list_assets(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节素材列表"""
    service = DossierService(db)
    assets = await service.list_chapter_assets(chapter_id)
    return success_response(
        data=[AssetResponse.model_validate(a) for a in assets],
        message="获取成功"
    )


@router.delete("/assets/{asset_id}", response_model=dict)
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除素材"""
    service = DossierService(db)
    success = await service.delete_asset(asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="素材不存在")
    return success_response(message="删除成功")


@router.patch("/assets/{asset_id}", response_model=dict)
async def update_asset_category(
    asset_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """更新素材的分类"""
    asset = await db.get(ChapterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    
    category_id = body.get("category_id")
    asset.category_id = category_id if category_id else None
    await db.commit()
    result = await db.execute(
        select(ChapterAsset).where(ChapterAsset.id == asset_id)
    )
    asset = result.scalar_one()
    
    return success_response(
        data={
            "id": str(asset.id),
            "category_id": str(asset.category_id) if asset.category_id else None,
        },
        message="分类已更新",
    )


# ====== Export ======

@router.post("/products/{dossier_id}/export", response_model=dict)
async def export_dossier(
    dossier_id: UUID,
    data: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """导出品种资料"""
    service = DossierService(db)
    result = await service.export_dossier(dossier_id, data.chapter_ids)
    
    if result["success"]:
        return success_response(data=result, message=result["message"])
    else:
        return error_response(message=result["message"])


@router.get("/products/{dossier_id}/download")
async def download_exported_file(
    dossier_id: UUID,
    filename: str = Query(..., description="文件名"),
    db: AsyncSession = Depends(get_db),
):
    """下载导出的文件"""
    service = DossierService(db)
    dossier = await service.repo.get_product_dossier(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    
    from pathlib import Path
    file_path = Path(dossier.outputs_path) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@router.get("/chapters/{chapter_id}/preview", response_model=dict)
async def get_chapter_preview(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节预览内容"""
    service = DossierService(db)
    result = await service.get_chapter_preview(chapter_id)
    
    if result["success"]:
        return success_response(data=result, message="获取预览成功")
    else:
        return error_response(message=result["message"])


@router.get("/chapters/{chapter_id}/docx-file")
async def get_chapter_docx_file(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节的 docx 工作副本文件，用于前端 docx-preview 渲染"""
    from pathlib import Path
    
    chapter = await db.get(DossierChapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    dossier = await db.get(ProductDossier, chapter.product_dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    
    if not chapter.working_file:
        raise HTTPException(status_code=404, detail="该章节尚无工作副本文件")
    
    file_path = Path(dossier.working_path) / chapter.working_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="工作副本文件不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=chapter.working_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.post("/products/{dossier_id}/match-assets", response_model=dict)
async def match_assets_to_chapters(
    dossier_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """智能匹配素材到章节"""
    service = DossierService(db)
    result = await service.match_assets_to_chapters(dossier_id)
    
    if result["success"]:
        return success_response(data=result, message=result["message"])
    else:
        return error_response(message=result["message"])

# ====== Field Mapping ======

from .field_fill_service import FieldFillService
# from .field_mapping_config import S6_FIELD_MAPPINGS  # 已废弃


@router.post("/chapters/{chapter_id}/fill-fields", response_model=dict)
async def fill_chapter_fields(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """执行字段填充 - 从素材提取内容并填充到章节"""
    service = DossierService(db)
    fill_service = FieldFillService(db)
    
    # 获取章节信息
    chapter = await service.get_chapter_detail(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 获取品种信息
    dossier = await service.get_product_dossier(chapter.product_dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="品种资料不存在")
    
    # 获取章节素材
    assets = await service.list_chapter_assets(chapter_id)
    
    # 执行填充
    result = await fill_service.fill_chapter_fields(dossier, chapter, assets)
    
    return success_response(
        data=result,
        message=result["message"]
    )


@router.get("/chapters/{chapter_code}/field-mappings", response_model=dict)
async def get_field_mappings(
    chapter_code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取章节的字段映射配置"""
    fill_service = FieldFillService(db)
    mappings = await fill_service.get_field_mappings(chapter_code)
    
    return success_response(
        data=[
            {
                "id": str(m.id),
                "field_name": m.field_name,
                "field_type": m.field_type,
                "location_type": m.location_type,
                "location_hint": m.location_hint,
                "extraction_prompt": m.extraction_prompt,
                "source_type": m.source_type,
                "source_category": m.source_category,
                "fixed_value": m.fixed_value,
                "appendix_slot": m.appendix_slot,
                "sort_order": m.sort_order,
                "is_required": m.is_required
            }
            for m in mappings
        ],
        message="获取成功"
    )


@router.post("/field-mappings/init-s6", response_model=dict)
async def init_s6_field_mappings(
    db: AsyncSession = Depends(get_db),
):
    """初始化 S.6 包装系统的字段映射配置（从数据库 seed 数据）"""
    from .service import DossierService
    service = DossierService(db)
    result = await service.init_chapter_ai_config("3.2.S.6")
    return success_response(data=result, message=result["message"])


@router.get("/chapters/{chapter_id}/fill-results", response_model=dict)
async def get_fill_results(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取章节的填充结果"""
    from .field_models import FieldFillResult
    
    stmt = select(FieldFillResult).where(
        FieldFillResult.chapter_id == chapter_id,
        FieldFillResult.is_deleted == False
    ).order_by(FieldFillResult.created_at.desc())
    
    result = await db.execute(stmt)
    fills = list(result.scalars().all())
    
    return success_response(
        data=[
            {
                "id": str(f.id),
                "field_name": f.field_name,
                "filled_value": f.filled_value,
                "fill_method": f.fill_method,
                "status": f.status,
                "created_at": f.created_at.isoformat() if f.created_at else None
            }
            for f in fills
        ],
        message="获取成功"
    )


# ====== AI Fill Service ======

@router.post("/chapters/{chapter_id}/ai-preview", response_model=dict)
async def ai_preview_extraction(
    chapter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """AI 智能解析预览：提取素材中的字段值（不写入文档）"""
    from .ai_fill_service import AIFillService
    from .models import DossierChapter, ProductDossier, ChapterAsset
    
    # 获取章节和品种信息
    stmt = select(DossierChapter).where(DossierChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        return error_response(message="章节不存在", status_code=404)
    
    stmt = select(ProductDossier).where(ProductDossier.id == chapter.product_dossier_id)
    result = await db.execute(stmt)
    dossier = result.scalar_one_or_none()
    
    if not dossier:
        return error_response(message="品种资料不存在", status_code=404)
    
    service = AIFillService(db)
    result = await service.preview_extraction(dossier, chapter)
    
    if not result["success"]:
        return error_response(message=result["message"])
    
    return success_response(data=result, message=result["message"])


@router.post("/chapters/{chapter_id}/ai-confirm", response_model=dict)
async def ai_confirm_and_fill(
    chapter_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """AI 填充确认：用户确认后写入文档"""
    from .ai_fill_service import AIFillService
    from .models import DossierChapter, ProductDossier, ChapterAsset
    
    # 获取章节和品种信息
    stmt = select(DossierChapter).where(DossierChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        return error_response(message="章节不存在", status_code=404)
    
    stmt = select(ProductDossier).where(ProductDossier.id == chapter.product_dossier_id)
    result = await db.execute(stmt)
    dossier = result.scalar_one_or_none()
    
    if not dossier:
        return error_response(message="品种资料不存在", status_code=404)
    
    user_confirmed_fields = data.get("fields", [])
    
    service = AIFillService(db)
    result = await service.confirm_and_fill(dossier, chapter, user_confirmed_fields)
    
    if not result["success"]:
        return error_response(message=result["message"])
    
    return success_response(data=result, message=result["message"])


@router.get("/chapters/{chapter_code}/asset-categories", response_model=dict)
async def get_asset_categories(
    chapter_code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取章节的素材分类列表"""
    from .ai_fill_service import AIFillService
    
    service = AIFillService(db)
    categories = await service.get_asset_categories(chapter_code)
    
    return success_response(data=categories, message="获取成功")


@router.post("/assets/{asset_id}/split-preview", response_model=dict)
async def split_preview(
    asset_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """AI 拆分预览：识别多页 PDF 每页的类型"""
    from .ai_fill_service import AIFillService
    from .models import ChapterAsset
    
    stmt = select(ChapterAsset).where(ChapterAsset.id == asset_id)
    result = await db.execute(stmt)
    asset = result.scalar_one_or_none()
    
    if not asset:
        return error_response(message="素材不存在", status_code=404)
    
    available_appendix_slots = data.get("available_appendix_slots", [])
    
    service = AIFillService(db)
    result = await service.preview_page_splits(asset, available_appendix_slots)
    
    if not result["success"]:
        return error_response(message=result["message"])
    
    return success_response(data=result, message=result["message"])


@router.post("/chapters/{chapter_id}/split-confirm", response_model=dict)
async def split_confirm_and_insert(
    chapter_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """AI 拆分确认：将各页转为图片插入模板"""
    from .ai_fill_service import AIFillService
    from .models import DossierChapter, ProductDossier, ChapterAsset
    
    stmt = select(DossierChapter).where(DossierChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        return error_response(message="章节不存在", status_code=404)
    
    stmt = select(ProductDossier).where(ProductDossier.id == chapter.product_dossier_id)
    result = await db.execute(stmt)
    dossier = result.scalar_one_or_none()
    
    if not dossier:
        return error_response(message="品种资料不存在", status_code=404)
    
    splits = data.get("splits", [])
    
    service = AIFillService(db)
    result = await service.confirm_page_splits_and_insert(dossier, chapter, splits)
    
    if not result["success"]:
        return error_response(message=result["message"])
    
    return success_response(data=result, message=result["message"])


@router.get("/chapters/{chapter_code}/appendix-slots", response_model=dict)
async def get_appendix_slots(
    chapter_code: str,
    db: AsyncSession = Depends(get_db),
):
    """获取章节的所有附录位置（从 FieldMapping 汇总）"""
    from .field_models import FieldMapping
    from sqlalchemy import select, and_
    
    stmt = select(FieldMapping).where(
        and_(
            FieldMapping.chapter_code == chapter_code,
            FieldMapping.appendix_slot.isnot(None),
            FieldMapping.is_deleted == False
        )
    )
    result = await db.execute(stmt)
    mappings = result.scalars().all()
    
    slots = sorted(set(m.appendix_slot for m in mappings if m.appendix_slot))
    return success_response(data=slots, message="获取成功")




