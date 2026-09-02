"""Validation API endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.schemas.statistics import ValidationStatistics
from app.modules.quality.schemas.validation import (
    CreateValidationRequest,
    UpdateValidationExecutionRequest,
    UpdateValidationRequest,
    ValidationDetail,
    ValidationExecutionListItem,
    ValidationListItem,
)
from app.modules.quality.service.quality_feishu_pages import (
    create_validation_record_in_feishu,
    delete_validation_record_in_feishu,
    get_validation_record_from_feishu,
    get_validation_statistics_from_feishu,
    list_validation_records_from_feishu,
    pull_validation_records_from_feishu,
    update_validation_record_in_feishu,
)
from app.modules.quality.service.validation import (
    batch_delete_validations,
    create_validation,
    delete_validation,
    get_validation_detail,
    get_validation_execution_list,
    get_validation_list,
    get_validation_statistics,
    update_validation,
    update_validation_execution,
)
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()


@router.get(
    "/validations",
    summary="获取验证列表",
    response_model=ApiResponseEnvelope[list[ValidationListItem]],
)
async def list_validations(
    validation_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    record_code: str | None = None,
    department: str | None = None,
    planned_end_date_from: str | None = None,
    planned_end_date_to: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await get_validation_list(
        db,
        validation_type=validation_type,
        status=status,
        keyword=keyword,
        record_code=record_code,
        department=department,
        planned_end_date_from=planned_end_date_from,
        planned_end_date_to=planned_end_date_to,
        drafted_at_from=drafted_at_from,
        drafted_at_to=drafted_at_to,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=result["items"],
        page=page,
        page_size=page_size,
        total=result["total"],
    )


# ══════════════════════════════════════════════
#  飞书验证与确认 API（直连飞书 Base）
# ══════════════════════════════════════════════


@router.get(
    "/feishu/validations",
    summary="从飞书获取验证记录列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def list_feishu_validations(
    validation_type: str | None = Query(None, description="验证类型"),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    record_code: str | None = Query(None),
    department: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空读总表"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await list_validation_records_from_feishu(
        db,
        validation_type=validation_type,
        status=status,
        keyword=keyword,
        record_code=record_code,
        department=department,
        year=year,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=result["items"],
        page=page,
        page_size=page_size,
        total=result["total"],
    )


@router.get(
    "/feishu/validations/{record_id}",
    summary="从飞书获取单条验证记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def get_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空读总表"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    detail = await get_validation_record_from_feishu(
        db, record_id, validation_type, year
    )
    return success_response(data=detail)


@router.post(
    "/feishu/validations",
    summary="在飞书中创建验证记录",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def create_feishu_validation(
    payload: dict[str, Any] = Body(..., description="验证记录数据"),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空写总表"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await create_validation_record_in_feishu(db, payload, year)
    return success_response(data=result, message="创建成功", status_code=201)


@router.put(
    "/feishu/validations/{record_id}",
    summary="在飞书中更新验证记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def update_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空写总表"),
    payload: dict[str, Any] = Body(..., description="验证记录更新数据"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await update_validation_record_in_feishu(
        db, record_id, payload, validation_type=validation_type, year=year
    )
    return success_response(data=result, message="更新成功")


@router.delete(
    "/feishu/validations/{record_id}",
    summary="在飞书中删除验证记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空写总表"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user_id = _require_user(current_user)
    await delete_validation_record_in_feishu(
        db, record_id, validation_type, actor_user_id=user_id, year=year
    )
    return success_response(message="删除成功")


@router.post(
    "/feishu-sync/validations/pull",
    summary="从飞书拉取验证记录同步到本地",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def pull_feishu_validations(
    validation_type: str | None = Query(None, description="验证类型"),
    year: int | None = Query(None, ge=2000, le=2100, description="年度表，留空读总表"),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await pull_validation_records_from_feishu(
        db, validation_type=validation_type, year=year
    )
    return success_response(data=result, message="拉取完成")


@router.post(
    "/validations/batch-delete",
    summary="批量删除验证主计划记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def batch_delete_validation_endpoint(
    validation_ids: list[uuid.UUID],
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await batch_delete_validations(db, validation_ids)
    return success_response(data=result, message="批量删除成功")


@router.post(
    "/validations",
    summary="创建验证记录",
    response_model=ApiResponseEnvelope[list[ValidationListItem]],
)
async def create_validation_endpoint(
    data: CreateValidationRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    try:
        result = await create_validation(db, data, "system")
    except ValueError as exc:
        status_code = 409 if "已存在" in str(exc) else 400
        raise AppException(message=str(exc), status_code=status_code) from exc
    return success_response(data=result, message="创建成功")


@router.get(
    "/validations/{validation_id}",
    summary="获取验证记录详情",
    response_model=ApiResponseEnvelope[ValidationDetail],
)
async def get_validation(
    validation_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    try:
        detail = await get_validation_detail(db, validation_id)
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=404) from exc
    return success_response(data=detail.model_dump())


@router.put(
    "/validations/{validation_id}",
    summary="更新验证记录",
    response_model=ApiResponseEnvelope[ValidationDetail],
)
async def update_validation_endpoint(
    validation_id: uuid.UUID,
    data: UpdateValidationRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    try:
        result = await update_validation(db, validation_id, data, "system")
    except ValueError as exc:
        status_code = (
            409 if "已存在" in str(exc) else 404 if "not found" in str(exc) else 400
        )
        raise AppException(message=str(exc), status_code=status_code) from exc
    return success_response(data=result, message="更新成功")


@router.delete(
    "/validations/{validation_id}",
    summary="删除验证记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_validation_endpoint(
    validation_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    try:
        result = await delete_validation(db, validation_id)
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=404) from exc
    return success_response(data=result, message="删除成功")


@router.get(
    "/validation-executions/{validation_type}",
    summary="获取验证执行列表",
    response_model=ApiResponseEnvelope[list[ValidationExecutionListItem]],
)
async def list_validation_executions(
    validation_type: str,
    status: str | None = None,
    keyword: str | None = None,
    department: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await get_validation_execution_list(
        db,
        validation_type=validation_type,
        status=status,
        keyword=keyword,
        department=department,
        drafted_at_from=drafted_at_from,
        drafted_at_to=drafted_at_to,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=result["items"],
        page=page,
        page_size=page_size,
        total=result["total"],
    )


@router.put(
    "/validation-executions/{validation_type}/{record_id}",
    summary="更新验证执行记录",
    response_model=ApiResponseEnvelope[ValidationExecutionListItem],
)
async def update_validation_execution_endpoint(
    validation_type: str,
    record_id: uuid.UUID,
    data: UpdateValidationExecutionRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["validation_qa"],
    )
    try:
        result = await update_validation_execution(
            db,
            validation_type=validation_type,
            record_id=record_id,
            data=data,
            user_id="system",
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=404) from exc
    return success_response(data=result, message="更新成功")


@router.get(
    "/statistics/validations",
    summary="获取验证统计",
    response_model=ApiResponseEnvelope[ValidationStatistics],
)
async def get_validation_statistics_endpoint(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await get_validation_statistics(db)
    return success_response(data=result)


@router.get(
    "/feishu/statistics/validations",
    summary="从飞书获取验证统计",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def get_feishu_validation_statistics_endpoint(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _require_user(current_user)
    result = await get_validation_statistics_from_feishu(db)
    return success_response(data=result)
