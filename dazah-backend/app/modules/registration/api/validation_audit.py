"""Validation Audit API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.modules.registration.schemas.validation_audit import (
    ValidationAuditFileListItem,
    ValidationAuditFileResponse,
    ValidationAuditIssueResponse,
    ValidationAuditReportResponse,
    ValidationAuditTaskCreate,
    ValidationAuditTaskListItem,
    ValidationAuditTaskResponse,
    ValidationAuditTaskUpdate,
)
from app.modules.registration.service.validation_audit import ValidationAuditService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 任务管理 ──────────────────────────────────────────────


@router.post("/tasks", response_model=dict, summary="创建审核任务")
async def create_task(
    data: ValidationAuditTaskCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ValidationAuditService(db)
    task = await service.create_task(data)
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
):
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
):
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
):
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
):
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)
    await service.delete_task(task)
    return success_response(message="删除成功")


# ── 文件管理 ──────────────────────────────────────────────


@router.post("/tasks/{task_id}/files", response_model=dict, summary="上传文件")
async def upload_files(
    task_id: UUID,
    files: list[UploadFile] = File(...),
    file_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """上传审核文件。file_type: protocol / report / attachment"""
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)

    results = []
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if ext not in ("docx", "pdf"):
            results.append({
                "filename": filename,
                "status": "failed",
                "error": "仅支持 .docx 和 .pdf 格式",
            })
            continue

        try:
            content = await upload_file.read()
            saved = await service.save_uploaded_file(task, filename, content, file_type)
            results.append({
                "file_id": str(saved.id),
                "filename": saved.original_filename,
                "file_size": saved.file_size,
                "status": "success",
            })
        except Exception as e:
            logger.exception("文件上传失败: %s", filename)
            results.append({
                "filename": filename,
                "status": "failed",
                "error": str(e),
            })

    return success_response(data=results, message="上传完成")


@router.get("/tasks/{task_id}/files", response_model=dict, summary="文件列表")
async def list_files(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
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


@router.post("/tasks/{task_id}/parse", response_model=dict, summary="解析文件")
async def parse_files(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)

    try:
        await service.parse_files(task)
        # Re-fetch task after status update
        task = await service.get_task(task_id)
        return success_response(
            data=ValidationAuditTaskResponse.model_validate(task),
            message="文件解析完成",
        )
    except RuntimeError as e:
        return error_response(message=str(e))


@router.post("/tasks/{task_id}/audit", response_model=dict, summary="执行审核")
async def run_audit(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ValidationAuditService(db)
    task = await service.get_task(task_id)
    if not task:
        return error_response(message="任务不存在", status_code=404)

    try:
        result = await service.run_audit(task)
        await service.save_issues(task, result)
        await service.generate_report(task, result)

        # Re-fetch task after updates
        task = await service.get_task(task_id)
        return success_response(
            data=ValidationAuditTaskResponse.model_validate(task),
            message="审核完成",
        )
    except RuntimeError as e:
        return error_response(message=str(e))


# ── 问题与报告 ────────────────────────────────────────────


@router.get("/tasks/{task_id}/issues", response_model=dict, summary="问题列表")
async def list_issues(
    task_id: UUID,
    issue_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
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
):
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
):
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
