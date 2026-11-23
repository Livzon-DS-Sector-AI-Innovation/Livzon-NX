"""Validation Audit API endpoints."""

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.core.response import error_response, success_response
from app.core.upload_security import MAX_UPLOAD_FILES, read_upload_secure
from app.modules.registration.schemas.validation_audit import (
    FileType,
    ValidationAuditErrorCode,
    ValidationAuditErrorResponse,
    ValidationAuditFileListItem,
    ValidationAuditIssueResponse,
    ValidationAuditReportResponse,
    ValidationAuditTaskCreate,
    ValidationAuditTaskListItem,
    ValidationAuditTaskResponse,
    ValidationAuditTaskUpdate,
    ValidationAuditUploadFailure,
    ValidationAuditUploadSuccess,
)
from app.modules.registration.service.validation_audit import ValidationAuditService
from app.platform.identity.deps import RequiredUser
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()


def _audit_error_response(*codes: ValidationAuditErrorCode) -> dict[str, Any]:
    return {
        "model": ValidationAuditErrorResponse,
        "description": f"可能的业务错误码：{', '.join(codes)}",
    }


# ── 任务管理 ──────────────────────────────────────────────


@router.post("/tasks", response_model=dict, summary="创建审核任务")
async def create_task(
    data: ValidationAuditTaskCreate,
    user: RequiredUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.create_task(data, created_by=user.id)
    return success_response(
        data=ValidationAuditTaskResponse.model_validate(task),
        message="创建成功",
    )


@router.get("/tasks", response_model=dict, summary="任务列表")
async def list_tasks(
    product_name: str | None = Query(None),
    source_company: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    items, total = await service.list_tasks(
        product_name=product_name,
        source_company=source_company,
        status=status,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data={
            "items": [ValidationAuditTaskListItem.model_validate(i) for i in items],
            "total": total,
        },
        meta={"page": page, "page_size": page_size, "total": total},
        message="获取成功",
    )


@router.get("/tasks/{task_id}", response_model=dict, summary="任务详情")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    return success_response(
        data=ValidationAuditTaskResponse.model_validate(task),
        message="获取成功",
    )


@router.put("/tasks/{task_id}", response_model=dict, summary="更新任务")
async def update_task(
    task_id: UUID,
    data: ValidationAuditTaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    updated = await service.update_task(task, data)
    return success_response(
        data=ValidationAuditTaskResponse.model_validate(updated),
        message="更新成功",
    )


@router.delete("/tasks/{task_id}", response_model=dict, summary="删除任务")
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    await service.delete_task(task)
    return success_response(message="删除成功")


# ── 文件管理 ──────────────────────────────────────────────


@router.post(
    "/tasks/{task_id}/files",
    response_model=ApiResponseEnvelope[
        list[ValidationAuditUploadSuccess | ValidationAuditUploadFailure]
    ],
    summary="上传文件",
    responses={400: _audit_error_response(ValidationAuditErrorCode.FILE_LIMIT)},
)
async def upload_files(
    task_id: UUID,
    files: list[UploadFile] = File(...),
    file_type: FileType = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """上传审核文件。file_type: protocol / report / attachment"""
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    if len(files) > MAX_UPLOAD_FILES:
        return error_response(
            message=f"单次最多上传 {MAX_UPLOAD_FILES} 个文件",
            status_code=400,
            detail={"error_code": ValidationAuditErrorCode.FILE_LIMIT.value},
        )

    results: list[ValidationAuditUploadSuccess | ValidationAuditUploadFailure] = []
    allowed_extensions = {".docx", ".pdf"}
    max_bytes = get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024
    for upload_file in files:
        filename = upload_file.filename or "未命名文件"
        try:
            if Path(filename).suffix.lower() not in allowed_extensions:
                raise AppException(status_code=415, message="文件格式不受支持")
            filename, content = await read_upload_secure(
                upload_file,
                max_bytes=max_bytes,
                allowed_extensions=allowed_extensions,
                what="验证审核文件",
            )
        except AppException as exc:
            results.append(
                ValidationAuditUploadFailure(
                    status="failed",
                    filename=filename,
                    status_code=exc.status_code,
                    error=exc.message,
                )
            )
            continue
        saved = await service.save_uploaded_file(
            task, filename, content, file_type.value
        )
        results.append(
            ValidationAuditUploadSuccess(
                status="success",
                file_id=saved.id,
                filename=saved.original_filename,
                file_size=saved.file_size,
            )
        )

    return success_response(data=results, message="上传完成")


@router.get("/tasks/{task_id}/files", response_model=dict, summary="文件列表")
async def list_files(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    files = await service.list_files(task_id)
    return success_response(
        data=[ValidationAuditFileListItem.model_validate(f) for f in files],
        message="获取成功",
    )


# ── 解析与审核 ────────────────────────────────────────────


@router.post(
    "/tasks/{task_id}/parse",
    response_model=dict,
    summary="解析文件",
    responses={
        409: _audit_error_response(ValidationAuditErrorCode.NO_FILES),
        422: _audit_error_response(ValidationAuditErrorCode.FILE_UNREADABLE),
    },
)
async def parse_files(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)

    try:
        await service.parse_files(task)
        # Re-fetch task after status update
        refreshed_task = await service.get_task(task_id)
        return success_response(
            data=ValidationAuditTaskResponse.model_validate(refreshed_task),
            message="文件解析完成",
        )
    except AppException as exc:
        if exc.status_code != 409:
            await service.mark_failed(task)
        raise


@router.post(
    "/tasks/{task_id}/audit",
    response_model=dict,
    summary="执行审核",
    responses={
        409: _audit_error_response(
            ValidationAuditErrorCode.NO_FILES,
            ValidationAuditErrorCode.NO_PARSED_FILES,
            ValidationAuditErrorCode.CROSS_FILES_REQUIRED,
        ),
        429: {"description": "审核服务限流"},
        502: {"description": "审核服务返回异常"},
        503: {"description": "审核服务暂时不可用"},
    },
)
async def run_audit(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)

    try:
        result = await service.run_audit(task)
        await service.save_issues(task, result)
        await service.generate_report(task, result)

        # Re-fetch task after updates
        refreshed_task = await service.get_task(task_id)
        return success_response(
            data=ValidationAuditTaskResponse.model_validate(refreshed_task),
            message="审核完成",
        )
    except LLMRateLimitError as exc:
        await service.mark_failed(task)
        raise AppException(status_code=429, message="审核服务请求过于频繁") from exc
    except LLMOutputError as exc:
        await service.mark_failed(task)
        raise AppException(status_code=502, message="审核服务返回异常") from exc
    except (LLMConfigError, LLMProviderError) as exc:
        await service.mark_failed(task)
        raise AppException(status_code=503, message="审核服务暂时不可用") from exc
    except AppException as exc:
        # 保存问题/生成报告任一环节失败：任务标记失败，
        # 避免停留 COMPLETED 却没有报告，重试也不会重复插入问题。
        if exc.status_code != 409:
            await service.mark_failed(task)
        raise


# ── 问题与报告 ────────────────────────────────────────────


@router.get("/tasks/{task_id}/issues", response_model=dict, summary="问题列表")
async def list_issues(
    task_id: UUID,
    issue_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    issues = await service.list_issues(task_id, issue_type=issue_type)
    return success_response(
        data=[ValidationAuditIssueResponse.model_validate(i) for i in issues],
        message="获取成功",
    )


@router.get("/tasks/{task_id}/report", response_model=dict, summary="审核报告")
async def get_report(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    report = await service.get_report(task_id)
    if not report:
        return error_response(message="报告尚未生成", status_code=404)
    return success_response(
        data=ValidationAuditReportResponse.model_validate(report),
        message="获取成功",
    )


@router.post("/tasks/{task_id}/export", response_model=dict, summary="导出报告")
async def export_report(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    report_path = await service.export_report(task_id)
    if not report_path:
        return error_response(message="报告尚未生成", status_code=404)

    import os

    if not os.path.exists(report_path):
        return error_response(message="报告文件不存在", status_code=404)

    return FileResponse(
        path=report_path,
        filename=os.path.basename(report_path),
        media_type="text/markdown",
    )
