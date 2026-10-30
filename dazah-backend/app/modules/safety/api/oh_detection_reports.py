"""Safety API — 职业健康检测报告导入与台账 endpoints。"""

from __future__ import annotations

import os
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.core.llm.exceptions import (
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.schemas.oh_detection_reports import (
    OhDetectionImportResponse,
    OhDetectionParsePreview,
    OhDetectionReportResponse,
    OhDetectionResultResponse,
)
from app.modules.safety.service.oh_detection_report import OhDetectionReportService
from app.shared.schemas import ApiResponseEnvelope

oh_detection_reports_router = APIRouter()

_PDF_MAX_BYTES = 30 * 1024 * 1024


async def _read_pdf(file: UploadFile) -> tuple[bytes, str]:
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise AppException(status_code=422, message="仅支持 PDF 格式的检测报告")
    content = await file.read()
    if not content:
        raise AppException(status_code=422, message="上传文件为空")
    if len(content) > _PDF_MAX_BYTES:
        raise AppException(status_code=422, message="检测报告文件不能超过 30MB")
    return content, file.filename or "report.pdf"


def _map_llm_error(exc: Exception) -> AppException:
    if isinstance(exc, LLMRateLimitError):
        return AppException(status_code=429, message="模型调用触发限流，请稍后重试")
    return AppException(status_code=502, message="AI 表格识别失败，请重试")


def _parse_detection_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise AppException(
            status_code=422, message="检测日期格式应为 YYYY-MM-DD"
        ) from exc


@oh_detection_reports_router.post(
    "/oh-detection-reports/parse",
    response_model=ApiResponseEnvelope[OhDetectionParsePreview],
    summary="解析检测报告 PDF（预览，不落库）",
)
async def parse_oh_detection_report(
    file: UploadFile = File(..., description="检测报告 PDF"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[OhDetectionParsePreview]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    pdf_bytes, file_name = await _read_pdf(file)
    service = OhDetectionReportService(db)
    try:
        preview = await service.parse_preview(pdf_bytes, file_name)
    except (LLMRateLimitError, LLMProviderError, LLMOutputError) as exc:
        raise _map_llm_error(exc) from exc
    return ApiResponseEnvelope(data=preview)


@oh_detection_reports_router.post(
    "/oh-detection-reports/import",
    response_model=ApiResponseEnvelope[OhDetectionImportResponse],
    summary="导入检测报告 PDF（同编号覆盖重导）",
)
async def import_oh_detection_report(
    file: UploadFile = File(..., description="检测报告 PDF"),
    report_no: str = Form("", description="报告编号（识别值可覆盖）"),
    report_name: str = Form(""),
    company_name: str = Form(""),
    detection_agency: str = Form(""),
    detection_date: str | None = Form(None, description="检测日期 YYYY-MM-DD"),
    remark: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[OhDetectionImportResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    pdf_bytes, file_name = await _read_pdf(file)
    service = OhDetectionReportService(db)
    try:
        report, imported_count, replaced, monitors_synced = (
            await service.import_report(
                pdf_bytes,
                file_name,
                report_no=report_no,
                report_name=report_name,
                company_name=company_name,
                detection_agency=detection_agency,
                detection_date=_parse_detection_date(detection_date),
                remark=remark,
                user_id=current_user.id,
            )
        )
    except (LLMRateLimitError, LLMProviderError, LLMOutputError) as exc:
        raise _map_llm_error(exc) from exc
    await db.commit()
    await db.refresh(report)
    return ApiResponseEnvelope(
        data=OhDetectionImportResponse(
            report=OhDetectionReportResponse.model_validate(report),
            imported_count=imported_count,
            replaced=replaced,
            monitors_synced=monitors_synced,
            skipped_tables=[
                {"table": item["table"], "reason": item["reason"]}
                for item in (report.parse_warnings or [])
                if item.get("reason", "").startswith("版式未识别")
            ],
        )
    )


@oh_detection_reports_router.get(
    "/oh-detection-reports",
    response_model=ApiResponseEnvelope,
    summary="检测报告列表（含全量统计）",
)
async def list_oh_detection_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    service = OhDetectionReportService(db)
    items, meta = await service.list_reports(page, page_size, keyword, year)
    return ApiResponseEnvelope(
        data=[OhDetectionReportResponse.model_validate(i) for i in items],
        meta={"page": page, "page_size": page_size, **meta},
    )


@oh_detection_reports_router.get(
    "/oh-detection-reports/{report_id}",
    response_model=ApiResponseEnvelope[OhDetectionReportResponse],
    summary="检测报告详情",
)
async def get_oh_detection_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[OhDetectionReportResponse]:
    service = OhDetectionReportService(db)
    report = await service.get_report(report_id)
    return ApiResponseEnvelope(data=OhDetectionReportResponse.model_validate(report))


@oh_detection_reports_router.get(
    "/oh-detection-reports/{report_id}/results",
    response_model=ApiResponseEnvelope,
    summary="检测报告结果明细（筛选分页）",
)
async def list_oh_detection_results(
    report_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    factor_category: str | None = None,
    record_type: str | None = None,
    workshop: str | None = None,
    verdict: str | None = None,
    is_noise_post: bool | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    service = OhDetectionReportService(db)
    items, total = await service.list_results(
        report_id,
        page,
        page_size,
        factor_category,
        record_type,
        workshop,
        verdict,
        is_noise_post,
        keyword,
    )
    return ApiResponseEnvelope(
        data=[OhDetectionResultResponse.model_validate(i) for i in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@oh_detection_reports_router.get(
    "/oh-detection-reports/{report_id}/file",
    response_model=None,
    summary="下载检测报告原始 PDF",
)
async def download_oh_detection_report_file(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> FileResponse:
    service = OhDetectionReportService(db)
    report = await service.get_report(report_id)
    if not report.source_file_path or not os.path.exists(report.source_file_path):
        raise AppException(status_code=404, message="原始报告文件不存在")
    return FileResponse(
        report.source_file_path,
        filename=report.source_file_name or "detection-report.pdf",
        media_type="application/pdf",
    )


@oh_detection_reports_router.delete(
    "/oh-detection-reports/{report_id}",
    response_model=ApiResponseEnvelope,
    summary="删除检测报告（软删除）",
)
async def delete_oh_detection_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    service = OhDetectionReportService(db)
    await service.delete_report(report_id, user_id=current_user.id)
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")
