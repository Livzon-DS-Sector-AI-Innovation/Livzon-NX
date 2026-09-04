"""验证方案与报告 AI 审核 API（/api/v1/quality/validation-reviews）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.jobs import get_job_status
from app.core.redis import cache_get, cache_set
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
    assert_quality_edit_scope,
    build_docx_download_headers,
    try_acquire_action_lock,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.models import ValidationReviewRecord
from app.modules.quality.schemas.validation_review import (
    ValidationReviewCreateRequest,
    ValidationReviewFileUploadedOut,
    ValidationReviewJobStatusResponse,
    ValidationReviewListItem,
    ValidationReviewOut,
    ValidationReviewRunOut,
)
from app.modules.quality.service.validation_review import (
    add_uploaded_review_file,
    build_review_list_item,
    build_review_out,
    create_review_record,
    delete_review_record,
    get_review_files,
    get_review_record,
    list_review_records,
    run_review,
)
from app.modules.quality.service.validation_review_export import build_review_docx
from app.platform.identity.rbac import resolve_user_permissions
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()

_REVIEW_SCOPE = QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"]
# 每分钟每位用户最多提交审核次数（控制 LLM 成本）
_RUN_RATE_LIMIT = 3


async def _assert_review_write(db: AsyncSession, current_user: CurrentUser) -> None:
    """写操作（创建/上传/发起/删除）准入：validation_qa 编辑权限。"""
    await assert_quality_edit_scope(
        db, current_user, scope_permission=_REVIEW_SCOPE
    )


async def _assert_review_view(
    db: AsyncSession, current_user: CurrentUser, record: ValidationReviewRecord
) -> None:
    """读操作（详情/导出）准入：记录归属本人，或具有质量 QA 权限。"""
    assert current_user is not None
    if record.created_by and str(record.created_by) == str(current_user.id):
        return
    permissions = await resolve_user_permissions(db, current_user.id)
    if (
        "*" in permissions
        or "quality:write" in permissions
        or _REVIEW_SCOPE in permissions
    ):
        return
    raise AppException(
        status_code=403, message="无权限查看该审核记录"
    )


async def _check_run_rate_limit(user_id: uuid.UUID) -> None:
    """每用户每分钟最多 _RUN_RATE_LIMIT 次审核提交（Redis 窗口计数）。"""
    key = f"quality:validation-review:run:{user_id}"
    raw = await cache_get(key)
    count = int(raw) if raw else 0
    if count >= _RUN_RATE_LIMIT:
        raise AppException(
            status_code=429, message="AI 审核提交过于频繁，请 1 分钟后再试"
        )
    await cache_set(key, str(count + 1), ex=60)


async def _can_view_all(db: AsyncSession, current_user: CurrentUser) -> bool:
    assert current_user is not None
    permissions = await resolve_user_permissions(db, current_user.id)
    return bool(
        "*" in permissions
        or "quality:write" in permissions
        or _REVIEW_SCOPE in permissions
    )


@router.post(
    "/validation-reviews",
    summary="新建验证 AI 审核会话",
    response_model=ApiResponseEnvelope[ValidationReviewOut],
)
async def create_review_endpoint(
    body: ValidationReviewCreateRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_review_write(db, current_user)
    record = await create_review_record(
        db,
        user_id=user_id,
        review_mode=body.review_mode,
        entry_id=body.entry_id,
        title=body.title,
    )
    await db.commit()
    files = await get_review_files(db, record.id)
    return success_response(data=build_review_out(record, files))


@router.post(
    "/validation-reviews/{review_id}/files",
    summary="上传 VP/VR 文档到审核会话",
    response_model=ApiResponseEnvelope[ValidationReviewFileUploadedOut],
)
async def upload_review_file_endpoint(
    review_id: uuid.UUID,
    file: UploadFile = File(...),
    doc_kind: str | None = Form(default=None),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_review_write(db, current_user)
    record = await get_review_record(db, review_id)
    row = await add_uploaded_review_file(
        db, record, file=file, doc_kind=doc_kind, user_id=user_id
    )
    await db.commit()
    return success_response(
        data={
            "id": str(row.id),
            "file_name": row.file_name,
            "doc_kind": row.doc_kind,
            "parse_status": row.parse_status,
        }
    )


@router.post(
    "/validation-reviews/{review_id}/run",
    summary="发起验证 AI 审核（后台任务）",
    response_model=ApiResponseEnvelope[ValidationReviewRunOut],
)
async def run_review_endpoint(
    review_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_review_write(db, current_user)
    record = await get_review_record(db, review_id)
    locked = await try_acquire_action_lock(
        f"validation-review:{review_id}", timeout=300
    )
    if not locked:
        raise AppException(
            status_code=429, message="该审核正在运行中，请勿重复操作"
        )
    await _check_run_rate_limit(user_id)
    job_id = await run_review(db, record, user_id=user_id)
    await db.commit()
    return success_response(data={"job_id": job_id, "review_id": str(record.id)})


@router.post(
    "/validation-reviews/{review_id}/rerun",
    summary="重新运行验证 AI 审核",
    response_model=ApiResponseEnvelope[ValidationReviewRunOut],
)
async def rerun_review_endpoint(
    review_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_review_write(db, current_user)
    record = await get_review_record(db, review_id)
    locked = await try_acquire_action_lock(
        f"validation-review:{review_id}", timeout=300
    )
    if not locked:
        raise AppException(
            status_code=429, message="该审核正在运行中，请勿重复操作"
        )
    await _check_run_rate_limit(user_id)
    job_id = await run_review(
        db, record, user_id=user_id, audit_action="validation_review.rerun"
    )
    await db.commit()
    return success_response(data={"job_id": job_id, "review_id": str(record.id)})


@router.get(
    "/validation-reviews/job/{job_id}",
    summary="查询验证 AI 审核任务进度与结果",
    response_model=ApiResponseEnvelope[ValidationReviewJobStatusResponse],
)
async def get_review_job_endpoint(
    job_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    status = await get_job_status(job_id)
    if status is None:
        raise NotFoundException(resource="审核任务", resource_id=job_id)
    if status.get("owner") and status.get("owner") != str(user_id):
        raise NotFoundException(resource="审核任务", resource_id=job_id)

    review_id: uuid.UUID | None = None
    record_status: str | None = None
    error_message: str | None = None
    if status.get("state") == "completed":
        result = await db.execute(
            select(ValidationReviewRecord).where(
                ValidationReviewRecord.job_id == job_id,
                ValidationReviewRecord.is_deleted.is_(False),
            )
        )
        record = result.scalars().first()
        if record:
            review_id = record.id
            record_status = record.status
            error_message = record.error_message

    data = ValidationReviewJobStatusResponse(
        job_id=job_id,
        state=str(status.get("state", "running")),
        progress=str(status.get("progress") or ""),
        status=record_status,
        error_message=error_message,
        review_id=review_id,
    ).model_dump(mode="json")
    return success_response(data=data)


@router.get(
    "/validation-reviews/{review_id}",
    summary="获取验证 AI 审核详情",
    response_model=ApiResponseEnvelope[ValidationReviewOut],
)
async def get_review_detail_endpoint(
    review_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    record = await get_review_record(db, review_id)
    await _assert_review_view(db, current_user, record)
    files = await get_review_files(db, review_id)
    return success_response(data=build_review_out(record, files))


@router.get(
    "/validation-reviews",
    summary="分页列出验证 AI 审核会话",
    response_model=ApiResponseEnvelope[list[ValidationReviewListItem]],
)
async def list_reviews_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    all_visible = await _can_view_all(db, current_user)
    records, total = await list_review_records(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        all_visible=all_visible,
    )
    items = []
    for record in records:
        files = await get_review_files(db, record.id)
        items.append(build_review_list_item(record, len(files)))
    return paginated_response(data=items, page=page, page_size=page_size, total=total)


@router.post(
    "/validation-reviews/{review_id}/export",
    summary="导出验证 AI 审核报告（docx）",
)
async def export_review_endpoint(
    review_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_user(current_user)
    record = await get_review_record(db, review_id)
    await _assert_review_view(db, current_user, record)
    files = await get_review_files(db, review_id)
    out_data = build_review_out(record, files)
    content = build_review_docx(out_data)
    filename = f"验证AI审核-{(record.title or '验证审核')[:40]}"
    headers = build_docx_download_headers(filename, "validation-review.docx")
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        headers=headers,
    )


@router.delete(
    "/validation-reviews/{review_id}",
    summary="删除验证 AI 审核会话（软删除）",
)
async def delete_review_endpoint(
    review_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    user_id = _require_user(current_user)
    await _assert_review_write(db, current_user)
    record = await get_review_record(db, review_id)
    await delete_review_record(db, record, user_id=user_id)
    await db.commit()
    return success_response(data={"id": str(record.id)}, message="已删除")
