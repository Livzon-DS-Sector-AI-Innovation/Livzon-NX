"""Document catalog API endpoints (各部门文件目录管理)."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import error_response, paginated_response, success_response
from app.core.upload_security import (
    MAX_UPLOAD_FILES,
    sniff_upload_mime,
    validate_upload_metadata,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    resolve_quality_list_scope as _resolve_quality_list_scope,
)
from app.modules.quality.api.uploads import read_upload_with_limit
from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.modules.quality.schemas.document_catalog import (
    BatchImportAttachmentResultItem,
    BatchImportDocumentAttachmentsResult,
    CreateDocumentDepartmentRequest,
    CreateDocumentEntryRequest,
    DocumentDepartmentOut,
    DocumentEntryLookupOut,
    DocumentEntryOut,
    DocumentEntryResolveItem,
    DocumentEntryResolveRequest,
    DocumentEntryResolveResult,
    ResolveAttachmentContent,
    UpdateDocumentDepartmentRequest,
    UpdateDocumentEntryRequest,
)
from app.modules.quality.service import document_catalog_crud as crud
from app.modules.quality.service.document_catalog import import_document_catalog
from app.modules.quality.service.document_catalog_attachment import (
    delete_attachment_from_entry,
    find_entry_by_file_name,
    read_attachment_preview,
    read_entry_md_contents,
    sync_entry_version,
    upload_attachment_to_entry,
)
from app.modules.quality.service.document_catalog_export import (
    export_document_catalog_docx,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()

IMPORT_MAX_SIZE = 20 * 1024 * 1024  # 20MB
DOCUMENT_CATALOG_EXTENSIONS = {
    ".md",
    ".doc",
    ".docx",
    ".wps",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
}
DOCUMENT_CATALOG_MIMES = {
    "text/markdown",
    # .md 文件内容嗅探结果为 text/plain，缺少该值会导致 md 导入被内容校验拒绝
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-works",
    "application/kswps",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
}
DOCUMENT_CATALOG_IMPORT_EXTENSIONS = {".xlsx", ".xls", ".docx", ".doc"}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/document-departments",
    summary="获取文件目录部门列表",
    response_model=ApiResponseEnvelope[list[DocumentDepartmentOut]],
)
async def list_document_departments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    departments, counts = await crud.list_document_departments(db)
    data = []
    for department in departments:
        item = DocumentDepartmentOut.model_validate(department).model_dump(
            mode="json"
        )
        item["document_count"] = counts.get(department.id, 0)
        data.append(item)
    return success_response(data=data)


@router.post(
    "/document-departments",
    summary="创建文件目录部门",
    response_model=ApiResponseEnvelope[DocumentDepartmentOut],
)
async def create_document_department(
    data: CreateDocumentDepartmentRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    department = await crud.create_document_department(db, data.name, data.sort_order)
    return success_response(
        data=DocumentDepartmentOut.model_validate(department).model_dump(
            mode="json"
        ),
        message="创建成功",
    )


@router.put(
    "/document-departments/{department_id}",
    summary="更新文件目录部门",
    response_model=ApiResponseEnvelope[DocumentDepartmentOut],
)
async def update_document_department(
    department_id: uuid.UUID,
    data: UpdateDocumentDepartmentRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    department = await crud.get_document_department(db, department_id)
    await _assert_quality_edit_scope(db, current_user, record=department)
    updated = await crud.update_document_department(
        db, department, data.model_dump(exclude_unset=True)
    )
    return success_response(
        data=DocumentDepartmentOut.model_validate(updated).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete(
    "/document-departments/{department_id}",
    summary="删除文件目录部门",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_document_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    department = await crud.get_document_department(db, department_id)
    await _assert_quality_edit_scope(db, current_user, record=department)
    await crud.delete_document_department(db, department)
    return success_response(message="已删除")


@router.get(
    "/document-entries/lookup-latest",
    summary="按文件名称查询最新版文件编号",
    response_model=ApiResponseEnvelope[list[DocumentEntryOut]],
)
async def lookup_latest_document_entry(
    name: str = Query(..., description="文件名称（核心名，去扩展名/附件编号前缀）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """供培训签到表录入《文件名称》（文件编号）时实时解析最新版编号.

    最新版判定：code 尾部修订号 /NN 最大 → 生效日期 → 更新时间。
    """
    _require_user(current_user)
    core = (name or "").strip()
    if not core:
        return success_response(data=None)
    entry = await crud.find_latest_entry_by_name(db, core)
    if entry is None:
        return success_response(data=None)
    return success_response(
        data=DocumentEntryLookupOut.model_validate(entry).model_dump(mode="json")
    )



@router.post(
    "/document-entries/resolve-content",
    summary="按文件名称批量解析条目并读取附件内容",
    response_model=DocumentEntryResolveResult,
)
async def resolve_document_entry_content(
    body: DocumentEntryResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """供培训口试 AI 出题使用：按文件名称解析最新版条目并读取附件标准 MD 内容。

    每个文件名称独立匹配：命中则返回条目 ID/编码/附件 MD 内容；未命中 matched=false。
    """
    _require_user(current_user)
    items: list[DocumentEntryResolveItem] = []
    for name in body.names:
        core = (name or "").strip()
        item = DocumentEntryResolveItem(name=core)
        if core:
            entry = await crud.find_latest_entry_by_name(db, core)
            if entry is not None:
                item.code = entry.code
                item.entry_id = entry.id
                item.matched = True
                item.attachments = [
                    ResolveAttachmentContent.model_validate(attachment)
                    for attachment in read_entry_md_contents(entry)
                ]
        items.append(item)
    return success_response(data=DocumentEntryResolveResult(results=items))


@router.get(
    "/document-entries",
    summary="获取文件目录条目列表",
    response_model=ApiResponseEnvelope[list[DocumentEntryOut]],
)
async def list_document_entries(
    department_id: uuid.UUID | None = Query(None, description="部门ID"),
    keyword: str | None = Query(None, description="关键词搜索（文件名称/编码）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    assert current_user is not None

    # 部门数据隔离：QA 角色全部可见，否则按部门名范围 → 文档部门目录 id 集合过滤
    scope = await _resolve_quality_list_scope(db, current_user)
    scope_dept_ids: list[str] | None = None
    if not scope.is_all and scope.department_names:
        dept_result = await db.execute(
            select(DocumentDepartment.id).where(
                DocumentDepartment.name.in_(scope.department_names),
                DocumentDepartment.is_deleted.is_(False),
            )
        )
        scope_dept_ids = [str(did) for did in dept_result.scalars().all()]
        if not scope_dept_ids:
            # 无可见部门目录：置不可能匹配的 id 保证空结果
            scope_dept_ids = ["00000000-0000-0000-0000-000000000000"]
    items, total = await crud.list_document_entries(
        db,
        department_id=department_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
        scope_dept_ids=scope_dept_ids,
    )
    return paginated_response(
        data=[
            DocumentEntryOut.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/document-entries",
    summary="创建文件目录条目",
    response_model=ApiResponseEnvelope[DocumentEntryOut],
)
async def create_document_entry(
    data: CreateDocumentEntryRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    entry = await crud.create_document_entry(db, data.model_dump())
    return success_response(
        data=DocumentEntryOut.model_validate(entry).model_dump(mode="json"),
        message="创建成功",
    )


@router.put(
    "/document-entries/{entry_id}",
    summary="更新文件目录条目",
    response_model=ApiResponseEnvelope[DocumentEntryOut],
)
async def update_document_entry(
    entry_id: uuid.UUID,
    data: UpdateDocumentEntryRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    entry = await crud.get_document_entry(db, entry_id)
    await _assert_quality_edit_scope(db, current_user, record=entry)
    updated = await crud.update_document_entry(
        db, entry, data.model_dump(exclude_unset=True)
    )
    return success_response(
        data=DocumentEntryOut.model_validate(updated).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete(
    "/document-entries/{entry_id}",
    summary="删除文件目录条目",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_document_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    entry = await crud.get_document_entry(db, entry_id)
    await _assert_quality_edit_scope(db, current_user, record=entry)
    await crud.delete_document_entry(db, entry)
    return success_response(message="已删除")


@router.post(
    "/document-catalog/import",
    summary="导入各部门文件目录（docx/xlsx/xls）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def import_document_catalog_excel(
    file: UploadFile = File(
        ..., description="各部门文件目录 .docx / .xlsx / .xls 文件"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        filename = validate_upload_metadata(
            file,
            allowed_extensions=DOCUMENT_CATALOG_IMPORT_EXTENSIONS,
        )
        content = await read_upload_with_limit(
            file,
            IMPORT_MAX_SIZE,
            "导入文件",
            allowed_extensions=DOCUMENT_CATALOG_IMPORT_EXTENSIONS,
        )
    except AppException:
        return error_response(
            message="仅支持 .xlsx / .xls / .docx / .doc 文件", status_code=400
        )
    try:
        result = await import_document_catalog(db, content, filename, filename=filename)
        return success_response(data=result, message="导入成功")
    except Exception:
        logger.exception("Failed to import document catalog")
        return error_response(message="导入失败，请稍后重试", status_code=400)


@router.get("/document-catalog/export", summary="导出文件目录 docx（复用留存标准模板）")
async def export_document_catalog(
    department_id: uuid.UUID | None = Query(None, description="部门ID"),
    department_name: str | None = Query(
        None, description="部门名称（用于匹配留存模板）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
        if department_id is not None:
            base_query = base_query.where(DocumentEntry.department_id == department_id)
        result = await db.execute(
            base_query.order_by(
                DocumentEntry.seq_no.asc().nulls_last(),
                DocumentEntry.created_at.asc(),
            )
        )
        entries = result.scalars().all()

        dept_name = department_name or ""
        if department_id is not None and not dept_name:
            dept_result = await db.execute(
                select(DocumentDepartment).where(
                    DocumentDepartment.id == department_id,
                    DocumentDepartment.is_deleted.is_(False),
                )
            )
            department = dept_result.scalar_one_or_none()
            dept_name = department.name if department else ""

        content = export_document_catalog_docx(list(entries), dept_name)
        filename = (
            f"{dept_name}文件目录_{datetime.now().strftime('%Y%m%d')}.docx"
            if dept_name
            else f"文件目录_{datetime.now().strftime('%Y%m%d')}.docx"
        )
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        }
        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            headers=headers,
        )
    except Exception:
        logger.exception("Failed to export document catalog")
        return error_response(message="导出文件目录失败，请稍后重试", status_code=500)


@router.post(
    "/document-catalog/attachments/import",
    summary="统一导入附件（自动识别名称/编号绑定条目，失败时 LLM 匹配；"
    "文件名版本高于条目时自动升级文件编码）",
    response_model=ApiResponseEnvelope[BatchImportDocumentAttachmentsResult],
)
async def batch_import_document_attachments(
    files: list[UploadFile] = File(
        ..., description="附件文件列表（.doc/.docx/.wps/.pdf/图片/.md）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    from app.modules.quality.service.document_catalog_attachment import (
        WORD_EXT,
        extract_content_identity,
        match_entry_for_attachment,
        upload_attachment_to_entry,
    )
    from app.modules.quality.service.document_catalog_md import (
        convert_word_attachment,
    )

    results: list[BatchImportAttachmentResultItem] = []
    bound = 0
    failed = 0
    version_updated_count = 0
    try:
        if len(files) > MAX_UPLOAD_FILES:
            raise AppException(
                message=f"单次最多上传 {MAX_UPLOAD_FILES} 个附件", status_code=400
            )
        for file in files:
            file_name = validate_upload_metadata(
                file,
                allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
                allowed_mimes=DOCUMENT_CATALOG_MIMES,
            )
            content = await read_upload_with_limit(
                file,
                IMPORT_MAX_SIZE,
                "附件",
                allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
                allowed_mimes=DOCUMENT_CATALOG_MIMES,
            )
            # word/md 先行转换：正文身份（编号/标题）参与匹配，转换结果复用避免二次转换
            content_identity: tuple[str | None, str | None] | None = None
            prepared = None
            ext = os.path.splitext(file_name)[1].lower()
            if ext in WORD_EXT:
                try:
                    prepared = await asyncio.to_thread(
                        convert_word_attachment, file_name, content
                    )
                    content_identity = extract_content_identity(prepared[0])
                except Exception:  # noqa: BLE001 转换失败仍按文件名匹配并原样存储
                    prepared = None
                    content_identity = None
            elif ext == ".md":
                content_identity = extract_content_identity(
                    content.decode("utf-8", errors="replace")
                )

            entry, match_type = await match_entry_for_attachment(
                db, file_name, content_identity
            )
            if entry is None:
                failed += 1
                results.append(BatchImportAttachmentResultItem(file_name=file_name))
                continue
            await upload_attachment_to_entry(
                db,
                entry,
                file_name,
                content,
                sniff_upload_mime(file_name, content),
                str(_require_user(current_user)),
                prepared=prepared,
            )
            bound += 1
            version_update = sync_entry_version(
                entry,
                file_name,
                rev_source=(
                    content_identity[0]
                    if match_type == "content" and content_identity
                    else None
                ),
            )
            if version_update is not None:
                version_updated_count += 1
            results.append(
                BatchImportAttachmentResultItem(
                    file_name=file_name,
                    matched=True,
                    match_type=match_type,
                    entry_id=entry.id,
                    entry_name=entry.name,
                    entry_code=entry.code,
                    version_updated=version_update is not None,
                    old_code=version_update.old_code if version_update else None,
                    new_code=version_update.new_code if version_update else None,
                )
            )
        return success_response(
            data=BatchImportDocumentAttachmentsResult(
                bound=bound,
                failed=failed,
                version_updated_count=version_updated_count,
                results=results,
            ),
            message=f"附件导入完成：成功 {bound} 个，未匹配 {failed} 个",
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to batch import document attachments")
        return error_response(message="批量上传附件失败，请稍后重试", status_code=400)


@router.post(
    "/document-entries/attachments/auto-bind",
    summary="按文件名编码自动绑定上传附件",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def auto_bind_document_entry_attachment(
    file: UploadFile = File(..., description="附件文件（.doc/.docx/.pdf/图片）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        file_name = validate_upload_metadata(
            file,
            allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
            allowed_mimes=DOCUMENT_CATALOG_MIMES,
        )
        entry = await find_entry_by_file_name(db, file_name)
        if entry is None:
            return error_response(
                message=f"未找到与「{file_name}」编码匹配的唯一文件条目，请选择具体条目后上传",
                status_code=404,
            )
        content = await read_upload_with_limit(
            file,
            IMPORT_MAX_SIZE,
            "附件",
            allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
            allowed_mimes=DOCUMENT_CATALOG_MIMES,
        )
        attachment = await upload_attachment_to_entry(
            db,
            entry,
            file_name,
            content,
            sniff_upload_mime(file_name, content),
            str(_require_user(current_user)),
        )
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.id == entry.id)
        )
        entry = result.scalar_one()
        return success_response(
            data={
                "entry_id": entry.id,
                "entry_name": entry.name,
                "matched": True,
                "attachment": attachment,
            },
            message="上传并绑定成功",
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to auto-bind document entry attachment")
        return error_response(message="上传附件失败，请稍后重试", status_code=400)


@router.post(
    "/document-entries/{entry_id}/attachments",
    summary="上传文件条目附件",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def upload_document_entry_attachment(
    entry_id: uuid.UUID,
    file: UploadFile = File(..., description="附件文件（.doc/.docx/.pdf/图片）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.id == entry_id,
                DocumentEntry.is_deleted.is_(False),
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return error_response(message="条目不存在", status_code=404)

        file_name = validate_upload_metadata(
            file,
            allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
            allowed_mimes=DOCUMENT_CATALOG_MIMES,
        )
        content = await read_upload_with_limit(
            file,
            IMPORT_MAX_SIZE,
            "附件",
            allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
            allowed_mimes=DOCUMENT_CATALOG_MIMES,
        )
        attachment = await upload_attachment_to_entry(
            db,
            entry,
            file_name,
            content,
            sniff_upload_mime(file_name, content),
            str(_require_user(current_user)),
        )
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.id == entry.id)
        )
        entry = result.scalar_one()
        return success_response(
            data={
                "entry_id": entry.id,
                "entry_name": entry.name,
                "matched": True,
                "attachment": attachment,
            },
            message="上传成功",
        )
    except AppException:
        raise
    except Exception:
        logger.exception("Failed to upload document entry attachment")
        return error_response(message="上传附件失败，请稍后重试", status_code=400)


@router.delete(
    "/document-entries/{entry_id}/attachments/{storage_key:path}",
    summary="删除文件条目附件",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_document_entry_attachment(
    entry_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.id == entry_id,
                DocumentEntry.is_deleted.is_(False),
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return error_response(message="条目不存在", status_code=404)

        removed = await delete_attachment_from_entry(db, entry, storage_key)
        if not removed:
            return error_response(message="附件不存在", status_code=404)
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete document entry attachment")
        return error_response(message="删除附件失败，请稍后重试", status_code=500)


@router.get(
    "/document-entries/{entry_id}/attachments/{storage_key:path}/content",
    summary="附件预览内容（word 返回标准 MD；图片/PDF 返回原文件）",
)
async def get_document_entry_attachment_content(
    entry_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.id == entry_id,
                DocumentEntry.is_deleted.is_(False),
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return error_response(message="条目不存在", status_code=404)

        data, content_type = read_attachment_preview(entry, storage_key)
        if not data:
            return error_response(message="附件内容不存在", status_code=404)
        return Response(content=data, media_type=content_type)
    except Exception:
        logger.exception("Failed to read document entry attachment content")
        return error_response(message="读取附件内容失败，请稍后重试", status_code=500)
