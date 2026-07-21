"""Validation API endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.quality.schemas.validation import (
    CreateValidationRequest,
    UpdateValidationRequest,
    UpdateValidationExecutionRequest,
)
from app.modules.quality.service.validation import (
    batch_delete_validations,
    create_validation,
    delete_validation,
    get_validation_detail,
    get_validation_execution_list,
    get_validation_list,
    get_validation_statistics,
    update_validation_execution,
    update_validation,
)
from app.modules.quality.service.quality_feishu_pages import (
    create_validation_record_in_feishu,
    delete_validation_record_in_feishu,
    get_validation_record_from_feishu,
    list_validation_records_from_feishu,
    pull_validation_records_from_feishu,
    update_validation_record_in_feishu,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_validation_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 400
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/validations", summary="获取验证列表")
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
    db: AsyncSession = Depends(get_db),
) -> dict:
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
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


# ══════════════════════════════════════════════
#  飞书验证与确认 API（直连飞书 Base）
# ══════════════════════════════════════════════


@router.get("/feishu/validations", summary="从飞书获取验证记录列表")
async def list_feishu_validations(
    validation_type: str | None = Query(None, description="验证类型"),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    record_code: str | None = Query(None),
    department: str | None = Query(None),
    planned_end_date_from: str | None = Query(None),
    planned_end_date_to: str | None = Query(None),
    drafted_at_from: str | None = Query(None),
    drafted_at_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await list_validation_records_from_feishu(
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
        return {
            "data": result["items"],
            "meta": {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
            },
        }
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.get("/feishu/validations/{record_id}", summary="从飞书获取单条验证记录")
async def get_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        detail = await get_validation_record_from_feishu(db, record_id, validation_type)
        return {"data": detail}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.post("/feishu/validations", summary="在飞书中创建验证记录")
async def create_feishu_validation(
    payload: dict = Body(..., description="验证记录数据"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await create_validation_record_in_feishu(db, payload)
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.put("/feishu/validations/{record_id}", summary="在飞书中更新验证记录")
async def update_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    payload: dict = Body(..., description="验证记录更新数据"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await update_validation_record_in_feishu(
            db, record_id, payload, validation_type=validation_type
        )
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.delete("/feishu/validations/{record_id}", summary="在飞书中删除验证记录")
async def delete_feishu_validation(
    record_id: str,
    validation_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await delete_validation_record_in_feishu(db, record_id, validation_type)
        return {"data": {"success": True}}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.post("/feishu-sync/validations/pull", summary="从飞书拉取验证记录同步到本地")
async def pull_feishu_validations(
    validation_type: str | None = Query(None, description="验证类型"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await pull_validation_records_from_feishu(db, validation_type=validation_type)
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.post("/validations/batch-delete", summary="批量删除验证主计划记录")
async def batch_delete_validation_endpoint(
    validation_ids: list[uuid.UUID],
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await batch_delete_validations(db, validation_ids)
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.post("/validations", summary="创建验证记录")
async def create_validation_endpoint(
    data: CreateValidationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await create_validation(db, data, "system")
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.get("/validations/{validation_id}", summary="获取验证记录详情")
async def get_validation(
    validation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        detail = await get_validation_detail(db, validation_id)
        return {"data": detail.model_dump()}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.put("/validations/{validation_id}", summary="更新验证记录")
async def update_validation_endpoint(
    validation_id: uuid.UUID,
    data: UpdateValidationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await update_validation(db, validation_id, data, "system")
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.delete("/validations/{validation_id}", summary="删除验证记录")
async def delete_validation_endpoint(
    validation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await delete_validation(db, validation_id)
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.get("/validation-executions/{validation_type}", summary="获取验证执行列表")
async def list_validation_executions(
    validation_type: str,
    status: str | None = None,
    keyword: str | None = None,
    department: str | None = None,
    drafted_at_from: str | None = None,
    drafted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
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
        return {
            "data": result["items"],
            "meta": {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
            },
        }
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.put("/validation-executions/{validation_type}/{record_id}", summary="更新验证执行记录")
async def update_validation_execution_endpoint(
    validation_type: str,
    record_id: uuid.UUID,
    data: UpdateValidationExecutionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await update_validation_execution(
            db,
            validation_type=validation_type,
            record_id=record_id,
            data=data,
            user_id="system",
        )
        return {"data": result}
    except ValueError as exc:
        raise _resolve_validation_error(exc)


@router.get("/statistics/validations", summary="获取验证统计")
async def get_validation_statistics_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await get_validation_statistics(db)
    return {"data": result.model_dump()}
