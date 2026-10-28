"""Safety API — regulations endpoints."""

import os
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.core.response import ApiResponse
from app.modules.safety.schemas import (
    OperationRegulationCreate,
    OperationRegulationResponse,
    OperationRegulationUpdate,
    RegulationBatchUploadResponse,
    RegulationLatestReviewEntry,
    RegulationReviewListResponse,
    RegulationReviewResponse,
    RegulationRevisionCreate,
    RegulationRevisionResponse,
    RegulationRevisionUpdate,
    SopContentUpdate,
    SopGenerateResponse,
)
from app.modules.safety.service import (
    RegulationComplianceService,
    RegulationService,
    SopGeneratorService,
)

regulations_router = APIRouter()


@regulations_router.get(
    "/regulations", response_model=ApiResponse, summary="获取安全操作规程列表"
)
async def get_regulations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    position: str | None = None,
    workshop: str | None = Query(None, description="车间/部门筛选"),
    keyword: str | None = None,
    status: str | None = Query(
        None, description="操规状态，逗号分隔多值: draft,generated,reviewed,exported"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取安全操作规程列表，支持按车间、岗位、关键词和状态筛选"""
    service = RegulationService(db)
    skip = (page - 1) * page_size
    items, total = await service.get_regulations(
        skip, page_size, position, keyword, status, workshop
    )
    return ApiResponse(
        data=[OperationRegulationResponse.model_validate(r) for r in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@regulations_router.get(
    "/regulations/{regulation_id}",
    response_model=ApiResponse,
    summary="获取安全操作规程详情",
)
async def get_regulation(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取安全操作规程详情，包含修订记录"""
    service = RegulationService(db)
    item = await service.get_regulation(regulation_id)
    if not item:
        return ApiResponse(code=404, message="操规不存在")
    return ApiResponse(data=OperationRegulationResponse.model_validate(item))


@regulations_router.post(
    "/regulations", response_model=ApiResponse, summary="创建安全操作规程"
)
async def create_regulation(
    data: OperationRegulationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建安全操作规程"""
    service = RegulationService(db)
    item = await service.create_regulation(data)
    await db.commit()
    return ApiResponse(data=OperationRegulationResponse.model_validate(item))


@regulations_router.put(
    "/regulations/{regulation_id}",
    response_model=ApiResponse,
    summary="更新安全操作规程",
)
async def update_regulation(
    regulation_id: uuid.UUID,
    data: OperationRegulationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新安全操作规程"""
    service = RegulationService(db)
    item = await service.update_regulation(regulation_id, data)
    if not item:
        return ApiResponse(code=404, message="操规不存在")
    await db.commit()
    return ApiResponse(data=OperationRegulationResponse.model_validate(item))


@regulations_router.delete(
    "/regulations/{regulation_id}",
    response_model=ApiResponse,
    summary="删除安全操作规程",
)
async def delete_regulation(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除安全操作规程"""
    service = RegulationService(db)
    result = await service.delete_regulation(regulation_id)
    if not result:
        return ApiResponse(code=404, message="操规不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


@regulations_router.post(
    "/regulations/{regulation_id}/upload",
    response_model=ApiResponse,
    summary="上传操规文档",
)
async def upload_regulation_document(
    regulation_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """上传操规文档并更新操规记录"""

    upload_dir = os.path.join("uploads", "safety", "regulations")
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename or ".md")[1]
    safe_name = f"{regulation_id}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = os.path.join(upload_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    service = RegulationService(db)
    item = await service.upload_regulation_document(
        regulation_id, file.filename or "unknown", file_path
    )
    if not item:
        return ApiResponse(code=404, message="操规不存在")
    await db.commit()
    return ApiResponse(data=OperationRegulationResponse.model_validate(item))


# ==================== 操规修订记录 Routes ====================


@regulations_router.get(
    "/revisions", response_model=ApiResponse, summary="获取修订记录列表"
)
async def get_revisions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    regulation_id: uuid.UUID | None = None,
    revision_type: str | None = None,
    review_opinion: str | None = None,
    revision_scope: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取修订记录列表，支持多条件筛选"""
    service = RegulationService(db)
    skip = (page - 1) * page_size
    items, total = await service.get_revisions(
        skip, page_size, regulation_id, revision_type, review_opinion, revision_scope
    )
    return ApiResponse(
        data=[RegulationRevisionResponse.model_validate(r) for r in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@regulations_router.get(
    "/revisions/{revision_id}",
    response_model=ApiResponse,
    summary="获取修订记录详情",
)
async def get_revision(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取修订记录详情，包含关联的危险源辨识记录"""
    service = RegulationService(db)
    item = await service.get_revision(revision_id)
    if not item:
        return ApiResponse(code=404, message="修订记录不存在")
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


@regulations_router.post(
    "/revisions", response_model=ApiResponse, summary="创建修订记录"
)
async def create_revision(
    data: RegulationRevisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建修订记录，自动从操规表获取旧文档链接"""
    service = RegulationService(db)
    item = await service.create_revision(data)
    if not item:
        return ApiResponse(code=404, message="关联的操规不存在")
    await db.commit()
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


@regulations_router.put(
    "/revisions/{revision_id}",
    response_model=ApiResponse,
    summary="更新修订记录",
)
async def update_revision(
    revision_id: uuid.UUID,
    data: RegulationRevisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新修订记录"""
    service = RegulationService(db)
    item = await service.update_revision(revision_id, data)
    if not item:
        return ApiResponse(code=404, message="修订记录不存在")
    await db.commit()
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


@regulations_router.delete(
    "/revisions/{revision_id}",
    response_model=ApiResponse,
    summary="删除修订记录",
)
async def delete_revision(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除修订记录"""
    service = RegulationService(db)
    result = await service.delete_revision(revision_id)
    if not result:
        return ApiResponse(code=404, message="修订记录不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ── 人工修订 ──


@regulations_router.post(
    "/revisions/{revision_id}/manual-complete",
    response_model=ApiResponse,
    summary="完成人工修订",
)
async def manual_revision_complete(
    revision_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """上传修订后的文档，完成人工修订流程：
    1. 保存新文档到 uploads/
    2. 更新修订记录（新文档链接 + 审核通过）
    3. 同步更新操规表文档链接
    """

    upload_dir = os.path.join("uploads", "safety", "regulations")
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename or ".md")[1]
    safe_name = f"revision_{revision_id}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = os.path.join(upload_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    service = RegulationService(db)
    item = await service.manual_revision_complete(revision_id, file_path, file.filename)
    if not item:
        return ApiResponse(
            code=400, message="无法完成修订，当前状态不允许或修订类型不是人工修订"
        )
    await db.commit()
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


# ── AI 修订 ──


@regulations_router.post(
    "/revisions/{revision_id}/ai-generate",
    response_model=ApiResponse,
    summary="AI生成修订版本",
)
async def ai_revision_generate(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """AI根据修订意见生成修订后的操规文档（返回供用户确认，不持久化）"""
    service = RegulationService(db)
    result = await service.ai_revision_generate(revision_id)
    if not result:
        return ApiResponse(
            code=400, message="无法生成，修订类型不是AI修订或修订记录不存在"
        )
    return ApiResponse(data=result)


@regulations_router.post(
    "/revisions/{revision_id}/ai-confirm",
    response_model=ApiResponse,
    summary="确认AI修订版本",
)
async def ai_revision_confirm(
    revision_id: uuid.UUID,
    generated_content: str = Query(..., description="AI生成的修订后完整内容"),
    document_name: str | None = Query(None, description="文档名称（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """用户确认AI生成的修订内容后，保存文档并更新所有关联记录"""
    service = RegulationService(db)
    item = await service.ai_revision_confirm(
        revision_id, generated_content, document_name
    )
    if not item:
        return ApiResponse(
            code=400, message="无法确认，修订类型不是AI修订或修订记录不存在"
        )
    await db.commit()
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


# ── 修订范围识别 ──


@regulations_router.post(
    "/revisions/{revision_id}/identify-scope",
    response_model=ApiResponse,
    summary="AI识别修订范围",
)
async def identify_revision_scope(
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """AI分析修订意见，识别修订范围（工艺/安全要求）。
    若识别出工艺变更，自动触发危险源辨识修订流程。
    """
    service = RegulationService(db)
    item = await service.identify_revision_scope(revision_id)
    if not item:
        return ApiResponse(code=404, message="修订记录不存在")
    await db.commit()
    return ApiResponse(data=RegulationRevisionResponse.model_validate(item))


# ═══════════════════════════════════════════════════════════════════
# SOP 标准化生成（调用 safety-sop-generator 插件）
# ═══════════════════════════════════════════════════════════════════


@regulations_router.post(
    "/regulations/generate",
    response_model=ApiResponse,
    summary="上传旧版操规并生成标准化版本",
)
async def generate_sop(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """上传旧版操规初稿（.docx），自动运行三层 pipeline 生成 9 章标准化操规。

    返回提取的元信息（产品/岗位/部门/编号）和完整 Markdown 内容，
    前端进入编辑面板供用户审阅修改。
    """
    if not file.filename or not file.filename.endswith(".docx"):
        return ApiResponse(code=400, message="仅支持 .docx 格式的操规初稿")

    service = SopGeneratorService(db)
    result = await service.generate_from_draft(file)
    await db.commit()

    return ApiResponse(data=SopGenerateResponse(**result).model_dump())


@regulations_router.get(
    "/regulations/{regulation_id}/content",
    response_model=ApiResponse,
    summary="获取操规标准化内容",
)
async def get_sop_content(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取操规的标准化 Markdown 内容，供编辑器加载。"""
    service = SopGeneratorService(db)
    result = await service.get_content(regulation_id)
    if not result:
        return ApiResponse(code=404, message="操规不存在")

    return ApiResponse(data=result)


@regulations_router.put(
    "/regulations/{regulation_id}/content",
    response_model=ApiResponse,
    summary="保存编辑后的操规内容",
)
async def update_sop_content(
    regulation_id: uuid.UUID,
    data: SopContentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """保存用户编辑后的标准化 Markdown 内容，可选更新状态。"""
    service = SopGeneratorService(db)
    item = await service.update_content(regulation_id, data.content, data.status)
    if not item:
        return ApiResponse(code=404, message="操规不存在")
    await db.commit()

    return ApiResponse(
        data={
            "regulation_id": str(regulation_id),
            "status": item.status if hasattr(item, "status") else "reviewed",
        },
        message="内容保存成功",
    )


@regulations_router.post(
    "/regulations/{regulation_id}/export",
    summary="导出标准化操规（可打印 HTML）",
)
async def export_sop_pdf(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """将存储的标准化 Markdown 渲染为带打印样式的 HTML，
    浏览器打开后自动弹出打印界面，可选择「另存为 PDF」。"""
    service = SopGeneratorService(db)
    html_text = await service.export_html(regulation_id)

    if not html_text:
        return ApiResponse(code=400, message="导出失败：操规不存在或内容为空")

    await db.commit()

    # Generate a friendly download filename (RFC 5987 encoded for non-ASCII chars)
    filename = f"标准化操规_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
    encoded_filename = quote(filename)

    return Response(
        content=html_text,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


# ═══════════════════════════════════════════════════════════════════
# 操规文档预览与下载
# ═══════════════════════════════════════════════════════════════════


@regulations_router.get(
    "/regulations/{regulation_id}/document-content",
    response_model=ApiResponse,
    summary="操规文档正文预览",
)
async def preview_regulation_document(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """提取操规上传文档的正文文本用于在线预览；
    文档缺失或不可提取时返回标准化内容并附说明。"""
    service = RegulationComplianceService(db)
    regulation = await service.get_regulation_for_document(regulation_id)
    if regulation is None:
        return ApiResponse(code=404, message="操规不存在")
    payload = await service.get_document_preview(regulation)
    return ApiResponse(data=payload)


@regulations_router.get(
    "/regulations/{regulation_id}/document",
    summary="下载操规原始文档",
)
async def download_regulation_document(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    service = RegulationComplianceService(db)
    regulation = await service.get_regulation_for_document(regulation_id)
    if regulation is None:
        return ApiResponse(code=404, message="操规不存在")
    document = service.get_document_file(regulation)
    if document is None:
        return ApiResponse(code=400, message="该操规尚未上传文档文件")
    file_path, download_name = document
    encoded_name = quote(download_name)
    return FileResponse(
        file_path,
        filename=download_name,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        },
    )


# ═══════════════════════════════════════════════════════════════════
# 操规批量导入（自动识别）与 AI 法规合规审核
# ═══════════════════════════════════════════════════════════════════


@regulations_router.post(
    "/regulations/batch-upload",
    response_model=ApiResponse,
    summary="批量上传操规文档并自动识别车间/岗位",
)
async def batch_upload_regulations(
    files: list[UploadFile] = File(
        ..., description="操规文档（docx/doc/docm/pdf/txt/md）"
    ),
    hint_workshop: str = Form(
        "", description="文件名未标明车间时的兜底车间/部门"
    ),
    use_ai: bool = Form(
        True,
        description="是否使用大模型辅助识别（不可用时自动回退规则识别）",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """批量导入车间操规文档：保存文件、提取正文、识别车间/岗位/名称，
    为每个文件创建操规台账记录（同一文件重复导入自动跳过）。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    if not files:
        raise AppException(status_code=400, message="请选择要导入的文件")
    if len(files) > 50:
        raise AppException(status_code=400, message="单次最多导入 50 个文件")

    payloads: list[tuple[str, bytes]] = []
    for file in files:
        content = await file.read()
        payloads.append((file.filename or "未命名.docx", content))

    service = RegulationComplianceService(db)
    items = await service.batch_upload(
        payloads,
        hint_workshop=hint_workshop,
        use_ai=use_ai,
        user_id=current_user.id,
    )
    await db.commit()

    response = RegulationBatchUploadResponse(
        items=items,
        success_count=sum(1 for item in items if item.ok),
        fail_count=sum(1 for item in items if not item.ok),
    )
    return ApiResponse(
        data=response.model_dump(),
        message=(
            f"导入完成：成功 {response.success_count} 个，"
            f"跳过/失败 {response.fail_count} 个"
        ),
    )


@regulations_router.post(
    "/regulations/{regulation_id}/compliance-review",
    response_model=ApiResponse,
    summary="对操规执行 AI 法规合规审核",
)
async def run_regulation_compliance_review(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """依据内置安全法规审核要点（安全生产法、危化品管理条例、GB 30871 等）
    对操规内容做 AI 合规审核，保存并返回审核报告（结论/评分/缺失项/不合规项）。
    AI 结论仅作辅助分析，整改与放行由人工确认。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")

    service = RegulationComplianceService(db)
    review = await service.run_compliance_review(
        regulation_id, user_id=current_user.id
    )
    await db.commit()
    payload = RegulationReviewResponse.model_validate(review)
    return ApiResponse(data=payload.model_dump())


@regulations_router.get(
    "/regulations/{regulation_id}/reviews",
    response_model=ApiResponse,
    summary="获取操规的合规审核记录",
)
async def list_regulation_reviews(
    regulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    service = RegulationComplianceService(db)
    reviews, total = await service.list_reviews(regulation_id)
    payload = RegulationReviewListResponse(
        items=[RegulationReviewResponse.model_validate(item) for item in reviews],
        total=total,
    )
    return ApiResponse(data=payload.model_dump())


@regulations_router.get(
    "/regulation-reviews/latest",
    response_model=ApiResponse,
    summary="批量获取操规最新审核状态",
)
async def get_latest_regulation_reviews(
    regulation_ids: str = Query(
        ..., description="操规ID列表，逗号分隔（最多 200 个）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    ids_raw = [part.strip() for part in regulation_ids.split(",") if part.strip()]
    if not ids_raw:
        return ApiResponse(data=[])
    if len(ids_raw) > 200:
        raise AppException(status_code=400, message="一次最多查询 200 条操规")
    try:
        ids = [uuid.UUID(value) for value in ids_raw]
    except ValueError as exc:
        raise AppException(status_code=400, message="操规ID格式不正确") from exc

    service = RegulationComplianceService(db)
    latest = await service.latest_reviews(ids)
    entries = [
        RegulationLatestReviewEntry(
            regulation_id=regulation_id,
            result=review.result,
            score=review.score,
            reviewed_at=review.created_at,
        ).model_dump(mode="json")
        for regulation_id, review in latest.items()
    ]
    return ApiResponse(data=entries)
