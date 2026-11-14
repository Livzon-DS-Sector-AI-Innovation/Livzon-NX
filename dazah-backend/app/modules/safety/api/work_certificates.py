"""Safety API — 人员特殊作业证件管理端点。

列表/详情/增删改 + 附件上传（同步返回 AI 识别建议，人工确认后回填）+
附件下载/预览 + 到期统计。AI 识别复用 msds 的建议值模式：
识别失败只返回原因，不影响附件保存。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.core.upload_security import read_upload_secure, sniff_upload_mime
from app.modules.safety.schemas.work_certificate import (
    CertificateExpirySummaryResponse,
    CertificateFileItem,
    CertificateImportPreview,
    CertificateImportResult,
    CertificateStatusOptionsResponse,
    CertificateUploadResponse,
    SpecialWorkCertificateCreate,
    SpecialWorkCertificateListResponse,
    SpecialWorkCertificateResponse,
    SpecialWorkCertificateUpdate,
)
from app.modules.safety.service import work_certificate as cert_service
from app.modules.safety.service import work_certificate_export as cert_export
from app.modules.safety.service.work_certificate_extract import (
    extract_certificate_suggestion,
)
from app.modules.safety.service.work_certificate_import import (
    ALLOWED_EXTENSIONS as IMPORT_ALLOWED_EXTENSIONS,
)
from app.modules.safety.service.work_certificate_import import (
    MAX_UPLOAD_SIZE as IMPORT_MAX_UPLOAD_SIZE,
)
from app.modules.safety.service.work_certificate_import import (
    CertificateImportService,
)
from app.modules.safety.service.work_permit_files import (
    CERTIFICATE_ALLOWED_EXTS,
    CERTIFICATE_MAX_BYTES,
    build_certificate_file_key,
    read_object,
    store_object,
)
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORIES,
)
from app.platform.storage.preview import resolve_preview_content
from app.shared.schemas import ApiResponseEnvelope

work_certificates_router = APIRouter()


@work_certificates_router.get(
    "/work-certificates/categories",
    response_model=ApiResponseEnvelope[CertificateStatusOptionsResponse],
    summary="证件类别字典",
)
async def list_certificate_categories(
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateStatusOptionsResponse]:
    return ApiResponseEnvelope(
        data=CertificateStatusOptionsResponse(categories=list(CERTIFICATE_CATEGORIES))
    )


@work_certificates_router.get(
    "/work-certificates/expiry-summary",
    response_model=ApiResponseEnvelope[CertificateExpirySummaryResponse],
    summary="证件到期统计（总数/有效/30天内到期/已过期）",
)
async def get_certificate_expiry_summary(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateExpirySummaryResponse]:
    return ApiResponseEnvelope(data=await cert_service.get_expiry_summary(db))


@work_certificates_router.get(
    "/work-certificates/export",
    response_model=None,
    summary="导出持证人员台账 Excel（按证件类别分子表，可再导入）",
)
async def export_work_certificates(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> StreamingResponse:
    content, filename = await cert_export.export_certificates_workbook(db)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{quote(filename)}")
        },
    )


@work_certificates_router.get(
    "/work-certificates",
    response_model=ApiResponseEnvelope[SpecialWorkCertificateListResponse],
    summary="证件分页列表（类别/状态/关键字/到期窗口）",
)
async def list_work_certificates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    certificate_category: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    expiring_days: int | None = Query(None, ge=0, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SpecialWorkCertificateListResponse]:
    data = await cert_service.list_certificates(
        db,
        page=page,
        page_size=page_size,
        certificate_category=certificate_category,
        status=status,
        keyword=keyword,
        expiring_days=expiring_days,
    )
    return ApiResponseEnvelope(data=data)


@work_certificates_router.post(
    "/work-certificates",
    response_model=ApiResponseEnvelope[SpecialWorkCertificateResponse],
    summary="创建证件",
)
async def create_work_certificate(
    payload: SpecialWorkCertificateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SpecialWorkCertificateResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    cert = await cert_service.create_certificate(db, payload, current_user)
    await db.commit()
    await db.refresh(cert)
    response = cert_service.to_response(cert)
    return ApiResponseEnvelope(data=response)


@work_certificates_router.put(
    "/work-certificates/{certificate_id}",
    response_model=ApiResponseEnvelope[SpecialWorkCertificateResponse],
    summary="更新证件（按有效期重算状态）",
)
async def update_work_certificate(
    certificate_id: UUID,
    payload: SpecialWorkCertificateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[SpecialWorkCertificateResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    cert = await cert_service.update_certificate(
        db, certificate_id, payload, current_user
    )
    await db.commit()
    await db.refresh(cert)
    return ApiResponseEnvelope(data=cert_service.to_response(cert))


@work_certificates_router.delete(
    "/work-certificates/{certificate_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除证件（软删除）",
)
async def delete_work_certificate(
    certificate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await cert_service.delete_certificate(db, certificate_id, current_user)
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@work_certificates_router.post(
    "/work-certificates/import/parse",
    response_model=ApiResponseEnvelope[CertificateImportPreview],
    summary="解析持证人员汇总表 Excel（预览子表与行数，不落库）",
)
async def parse_certificate_import(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateImportPreview]:
    file_name, content = await read_upload_secure(
        file,
        max_bytes=IMPORT_MAX_UPLOAD_SIZE,
        allowed_extensions=IMPORT_ALLOWED_EXTENSIONS,
        what="证件导入文件",
    )
    try:
        preview = await CertificateImportService(db).preview(file_name, content)
    except ValueError as exc:
        raise AppException(status_code=400, message=str(exc)) from exc
    return ApiResponseEnvelope(data=CertificateImportPreview.model_validate(preview))


@work_certificates_router.post(
    "/work-certificates/import",
    response_model=ApiResponseEnvelope[CertificateImportResult],
    summary="导入持证人员汇总表 Excel 到证件台账",
)
async def import_work_certificates(
    file: UploadFile,
    sheets: str = Form(
        "", description="要导入的子表名 JSON 数组，空则导入全部可识别子表"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateImportResult]:
    """按子表导入证件：同类别同证件号合并，与库内记录匹配后更新或新建。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    selected_sheets: list[str] | None = None
    if sheets:
        try:
            parsed_sheets = json.loads(sheets)
        except json.JSONDecodeError:
            raise AppException(status_code=400, message="子表参数格式错误") from None
        if not isinstance(parsed_sheets, list) or not all(
            isinstance(item, str) for item in parsed_sheets
        ):
            raise AppException(status_code=400, message="子表参数格式错误")
        selected_sheets = parsed_sheets

    file_name, content = await read_upload_secure(
        file,
        max_bytes=IMPORT_MAX_UPLOAD_SIZE,
        allowed_extensions=IMPORT_ALLOWED_EXTENSIONS,
        what="证件导入文件",
    )
    try:
        result = await CertificateImportService(db).commit(
            file_name, content, selected_sheets, current_user.id
        )
    except ValueError as exc:
        raise AppException(status_code=400, message=str(exc)) from exc
    await db.commit()
    return ApiResponseEnvelope(data=CertificateImportResult.model_validate(result))


@work_certificates_router.post(
    "/work-certificates/{certificate_id}/files",
    response_model=ApiResponseEnvelope[CertificateUploadResponse],
    summary="上传证件附件（附带 AI 识别字段建议）",
)
async def upload_certificate_file(
    certificate_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateUploadResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    file_name, content = await read_upload_secure(
        file,
        max_bytes=CERTIFICATE_MAX_BYTES,
        allowed_extensions=CERTIFICATE_ALLOWED_EXTS,
        what="证件附件",
    )
    content_type = sniff_upload_mime(file_name, content)
    cert = await cert_service.get_certificate(db, certificate_id)
    storage_key = store_object(
        "work-certificates",
        build_certificate_file_key(str(cert.id), Path(file_name).suffix.lower()),
        content,
        content_type,
    )
    file_obj = await cert_service.add_certificate_file(
        db,
        certificate_id,
        file_name=file_name,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(content),
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(file_obj)
    files = await cert_service.list_certificate_files(db, certificate_id)

    suggestion, ai_error = await extract_certificate_suggestion(
        file_name=file_name, content=content
    )
    return ApiResponseEnvelope(
        data=CertificateUploadResponse(
            file=CertificateFileItem.model_validate(file_obj),
            files=[CertificateFileItem.model_validate(item) for item in files],
            ai_suggestion=suggestion,
            ai_error=ai_error,
        )
    )


@work_certificates_router.post(
    "/work-certificates/{certificate_id}/files/{file_id}/extract",
    response_model=ApiResponseEnvelope[CertificateUploadResponse],
    summary="重新 AI 识别证件附件（返回字段建议）",
)
async def extract_certificate_file(
    certificate_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[CertificateUploadResponse]:
    file_obj = await cert_service.get_certificate_file(db, certificate_id, file_id)
    stored = read_object("work-certificates", file_obj.storage_key)
    if stored is None:
        raise NotFoundException("证件附件文件")
    suggestion, ai_error = await extract_certificate_suggestion(
        file_name=file_obj.file_name, content=stored[0]
    )
    files = await cert_service.list_certificate_files(db, certificate_id)
    return ApiResponseEnvelope(
        data=CertificateUploadResponse(
            file=CertificateFileItem.model_validate(file_obj),
            files=[CertificateFileItem.model_validate(item) for item in files],
            ai_suggestion=suggestion,
            ai_error=ai_error,
        )
    )


@work_certificates_router.get(
    "/work-certificates/{certificate_id}/files/{file_id}/content",
    response_model=None,
    summary="下载证件附件",
)
async def download_certificate_file(
    certificate_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    file_obj = await cert_service.get_certificate_file(db, certificate_id, file_id)
    stored = read_object("work-certificates", file_obj.storage_key)
    if stored is None:
        raise NotFoundException("证件附件文件")
    data, content_type = stored
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(file_obj.file_name)}"
            )
        },
    )


@work_certificates_router.get(
    "/work-certificates/{certificate_id}/files/{file_id}/preview",
    response_model=None,
    summary="证件附件在线预览",
)
async def preview_certificate_file(
    certificate_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    file_obj = await cert_service.get_certificate_file(db, certificate_id, file_id)
    stored = read_object("work-certificates", file_obj.storage_key)
    if stored is None:
        raise NotFoundException("证件附件文件")
    data, _content_type = stored
    try:
        preview_data, preview_type, preview_name = resolve_preview_content(
            data, file_obj.file_name
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=415) from exc
    return Response(
        content=preview_data,
        media_type=preview_type,
        headers={
            "Content-Disposition": (f"inline; filename*=UTF-8''{quote(preview_name)}")
        },
    )


@work_certificates_router.delete(
    "/work-certificates/{certificate_id}/files/{file_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除证件附件（软删除）",
)
async def delete_certificate_file(
    certificate_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await cert_service.delete_certificate_file(
        db, certificate_id, file_id, current_user
    )
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
