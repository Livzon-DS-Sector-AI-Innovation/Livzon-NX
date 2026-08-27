"""Document catalog API endpoints (各部门文件目录管理)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import error_response, paginated_response, success_response
from app.core.upload_security import (
    MAX_UPLOAD_FILES,
    sniff_upload_mime,
    validate_upload_metadata,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.api.uploads import read_upload_with_limit
from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.modules.quality.schemas.document_catalog import (
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
from app.modules.quality.service.document_catalog import import_document_catalog
from app.modules.quality.service.document_catalog_attachment import (
    delete_attachment_from_entry,
    find_entry_by_file_name,
    read_attachment_preview,
    read_entry_md_contents,
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
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
}
DOCUMENT_CATALOG_MIMES = {
    "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
    try:
        result = await db.execute(
            select(DocumentDepartment)
            .where(DocumentDepartment.is_deleted.is_(False))
            .order_by(
                DocumentDepartment.sort_order.asc(), DocumentDepartment.name.asc()
            )
        )
        departments = result.scalars().all()

        count_result = await db.execute(
            select(DocumentEntry.department_id, func.count(DocumentEntry.id))
            .where(DocumentEntry.is_deleted.is_(False))
            .group_by(DocumentEntry.department_id)
        )
        counts = {row[0]: row[1] for row in count_result.all()}

        data = []
        for department in departments:
            item = DocumentDepartmentOut.model_validate(department).model_dump(
                mode="json"
            )
            item["document_count"] = counts.get(department.id, 0)
            data.append(item)
        return success_response(data=data)
    except Exception:
        logger.exception("Failed to list document departments")
        return error_response(message="操作失败，请稍后重试", status_code=500)


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
    try:
        name = data.name.strip()
        result = await db.execute(
            select(DocumentDepartment).where(DocumentDepartment.name == name)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            if not existing.is_deleted:
                return error_response(message="该部门已存在", status_code=400)
            # 复活已软删除的同名部门
            existing.is_deleted = False
            existing.sort_order = data.sort_order
            await db.flush()
            result = await db.execute(
                select(DocumentDepartment).where(DocumentDepartment.id == existing.id)
            )
            existing = result.scalar_one()
            return success_response(
                data=DocumentDepartmentOut.model_validate(existing).model_dump(
                    mode="json"
                ),
                message="创建成功",
            )

        department = DocumentDepartment(name=name, sort_order=data.sort_order)
        db.add(department)
        await db.flush()
        return success_response(
            data=DocumentDepartmentOut.model_validate(department).model_dump(
                mode="json"
            ),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create document department")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


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
    try:
        result = await db.execute(
            select(DocumentDepartment).where(
                DocumentDepartment.id == department_id,
                DocumentDepartment.is_deleted.is_(False),
            )
        )
        department = result.scalar_one_or_none()
        if department is None:
            return error_response(message="部门不存在", status_code=404)

        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data:
            new_name = update_data["name"].strip()
            dup_result = await db.execute(
                select(DocumentDepartment).where(
                    DocumentDepartment.name == new_name,
                    DocumentDepartment.id != department_id,
                )
            )
            if dup_result.scalar_one_or_none() is not None:
                return error_response(message="该部门名称已存在", status_code=400)
            update_data["name"] = new_name

        for key, value in update_data.items():
            setattr(department, key, value)

        await db.flush()
        result = await db.execute(
            select(DocumentDepartment).where(DocumentDepartment.id == department.id)
        )
        department = result.scalar_one()
        return success_response(
            data=DocumentDepartmentOut.model_validate(department).model_dump(
                mode="json"
            ),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update document department")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


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
    try:
        result = await db.execute(
            select(DocumentDepartment).where(
                DocumentDepartment.id == department_id,
                DocumentDepartment.is_deleted.is_(False),
            )
        )
        department = result.scalar_one_or_none()
        if department is None:
            return error_response(message="部门不存在", status_code=404)

        department.is_deleted = True
        entry_result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.department_id == department_id,
                DocumentEntry.is_deleted.is_(False),
            )
        )
        for entry in entry_result.scalars().all():
            entry.is_deleted = True

        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete document department")
        return error_response(message="操作失败，请稍后重试", status_code=500)


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
    base = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))

    rows = (await db.execute(base.where(DocumentEntry.name == core))).scalars().all()
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(DocumentEntry.name.ilike(f"%{_escape_like(core)}%"))
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(func.strpos(literal(core), DocumentEntry.name) > 0)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return success_response(data=None)

    def sort_key(entry: DocumentEntry) -> Any:
        m = re.search(r"/(\d+)$", (entry.code or "").strip())
        rev = int(m.group(1)) if m else -1
        return (
            rev,
            entry.effective_date or date.min,
            entry.updated_at or datetime.min,
        )

    best = max(rows, key=sort_key)
    return success_response(
        data=DocumentEntryLookupOut.model_validate(best).model_dump(mode="json")
    )


async def _find_latest_entry_by_name(
    db: AsyncSession, core: str
) -> DocumentEntry | None:
    "按文件名称查找最新版条目（与 lookup-latest 相同匹配策略：精确→模糊→反向包含）。"
    base = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
    rows = (await db.execute(base.where(DocumentEntry.name == core))).scalars().all()
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(DocumentEntry.name.ilike(f"%{_escape_like(core)}%"))
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        rows = (
            (
                await db.execute(
                    base.where(func.strpos(literal(core), DocumentEntry.name) > 0)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return None

    def sort_key(entry: DocumentEntry) -> Any:
        m = re.search(r"/(\d+)$", (entry.code or "").strip())
        rev = int(m.group(1)) if m else -1
        return (
            rev,
            entry.effective_date or date.min,
            entry.updated_at or datetime.min,
        )

    return max(rows, key=sort_key)


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
            entry = await _find_latest_entry_by_name(db, core)
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
    from app.platform.identity.data_scope import resolve_user_department_scope

    # 部门数据隔离：部门名范围 → 文档部门目录 id 集合 → 条目过滤
    scope = await resolve_user_department_scope(db, current_user)
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
    try:
        base_query = select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
        count_query = (
            select(func.count())
            .select_from(DocumentEntry)
            .where(DocumentEntry.is_deleted.is_(False))
        )

        if scope_dept_ids is not None:
            base_query = base_query.where(
                DocumentEntry.department_id.in_(scope_dept_ids)
            )
            count_query = count_query.where(
                DocumentEntry.department_id.in_(scope_dept_ids)
            )

        if department_id is not None:
            base_query = base_query.where(DocumentEntry.department_id == department_id)
            count_query = count_query.where(
                DocumentEntry.department_id == department_id
            )

        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters = or_(
                DocumentEntry.name.ilike(pattern),
                DocumentEntry.code.ilike(pattern),
            )
            base_query = base_query.where(filters)
            count_query = count_query.where(filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        if department_id is None:
            base_query = base_query.join(
                DocumentDepartment,
                DocumentEntry.department_id == DocumentDepartment.id,
            )
            order_by: list[ColumnElement[Any]] = [
                DocumentDepartment.sort_order.asc(),
                DocumentEntry.seq_no.asc().nulls_last(),
                DocumentEntry.created_at.asc(),
            ]
        else:
            order_by = [
                DocumentEntry.seq_no.asc().nulls_last(),
                DocumentEntry.created_at.asc(),
            ]

        offset = (page - 1) * page_size
        result = await db.execute(
            base_query.order_by(*order_by).offset(offset).limit(page_size)
        )
        items = result.scalars().all()
        return paginated_response(
            data=[
                DocumentEntryOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list document entries")
        return error_response(message="操作失败，请稍后重试", status_code=500)


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
    try:
        dept_result = await db.execute(
            select(DocumentDepartment).where(
                DocumentDepartment.id == data.department_id,
                DocumentDepartment.is_deleted.is_(False),
            )
        )
        if dept_result.scalar_one_or_none() is None:
            return error_response(message="部门不存在", status_code=404)

        entry = DocumentEntry(**data.model_dump())
        db.add(entry)
        await db.flush()
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.id == entry.id)
        )
        entry = result.scalar_one()
        return success_response(
            data=DocumentEntryOut.model_validate(entry).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create document entry")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


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

        update_data = data.model_dump(exclude_unset=True)
        if "department_id" in update_data:
            dept_result = await db.execute(
                select(DocumentDepartment).where(
                    DocumentDepartment.id == update_data["department_id"],
                    DocumentDepartment.is_deleted.is_(False),
                )
            )
            if dept_result.scalar_one_or_none() is None:
                return error_response(message="部门不存在", status_code=404)

        for key, value in update_data.items():
            setattr(entry, key, value)

        await db.flush()
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.id == entry.id)
        )
        entry = result.scalar_one()
        return success_response(
            data=DocumentEntryOut.model_validate(entry).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update document entry")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


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

        entry.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete document entry")
        return error_response(message="操作失败，请稍后重试", status_code=500)


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
    summary="统一导入附件（自动识别名称/编号绑定条目，失败时 LLM 匹配）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def batch_import_document_attachments(
    files: list[UploadFile] = File(
        ..., description="附件文件列表（.doc/.docx/.pdf/图片/.md）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    from app.modules.quality.service.document_catalog_attachment import (
        match_entry_for_attachment,
        upload_attachment_to_entry,
    )

    results: list[dict[str, Any]] = []
    bound = 0
    failed = 0
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
            entry, match_type = await match_entry_for_attachment(db, file_name)
            if entry is None:
                failed += 1
                results.append(
                    {
                        "file_name": file_name,
                        "matched": False,
                        "match_type": "none",
                        "entry_id": None,
                        "entry_name": None,
                        "entry_code": None,
                    }
                )
                continue
            content = await read_upload_with_limit(
                file,
                IMPORT_MAX_SIZE,
                "附件",
                allowed_extensions=DOCUMENT_CATALOG_EXTENSIONS,
                allowed_mimes=DOCUMENT_CATALOG_MIMES,
            )
            await upload_attachment_to_entry(
                db,
                entry,
                file_name,
                content,
                sniff_upload_mime(file_name, content),
                str(_require_user(current_user)),
            )
            bound += 1
            results.append(
                {
                    "file_name": file_name,
                    "matched": True,
                    "match_type": match_type,
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "entry_code": entry.code,
                }
            )
        return success_response(
            data={"bound": bound, "failed": failed, "results": results},
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
