"""Supplier Qualification Feishu page API endpoints.

Provides CRUD + pull endpoints that operate directly on Feishu Bitable.
Follows backend spec: uses schemas, unified response format, and business exceptions.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
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
from app.modules.quality.schemas.supplier_qualification import (
    CreateSupplierQualificationRequest,
    SupplierDashboardStatsOut,
    SupplierPullResult,
    SupplierQualificationOut,
    UpdateSupplierQualificationRequest,
)
from app.modules.quality.service.quality_feishu_pages_supplier import (
    create_supplier_qualification_record,
    delete_supplier_qualification_record,
    get_supplier_statistics,
    list_supplier_qualification_records,
    pull_supplier_qualification_records,
    update_supplier_qualification_record,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/supplier-qualification",
    summary="获取供应商资质列表（飞书）",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_list_supplier_qualification(
    keyword: str | None = Query(None, description="关键词搜索"),
    supplier_name: str | None = Query(None, description="供应商名称筛选"),
    material_type: str | None = Query(None, description="物料类型筛选"),
    qualification_name: str | None = Query(None, description="资质名称筛选"),
    is_completed: bool | None = Query(None, description="是否完成"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await list_supplier_qualification_records(
            db,
            keyword=keyword,
            supplier_name=supplier_name,
            material_type=material_type,
            qualification_name=qualification_name,
            is_completed=is_completed,
            page=page,
            page_size=page_size,
        )
        # Validate and serialize each item
        validated_items = []
        for item in result["items"]:
            try:
                validated = SupplierQualificationOut.model_validate(item)
                validated_items.append(validated.model_dump(mode="json"))
            except AppException:
                raise
            except Exception as e:
                logger.warning(
                    f"Validation failed for item {item.get('record_id')}: {e}"
                )
                validated_items.append(item)  # Fall back to raw data

        return paginated_response(
            data=validated_items,
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except AppException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list supplier qualifications: {e}")
        raise AppException(status_code=500, message="服务暂时不可用，请稍后重试") from e


@router.post(
    "/supplier-qualification",
    summary="创建供应商资质记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_create_supplier_qualification(
    data: CreateSupplierQualificationRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await create_supplier_qualification_record(
            db, data.model_dump(mode="json")
        )
        return success_response(
            data=SupplierQualificationOut.model_validate(result).model_dump(
                mode="json"
            ),
            message="创建成功",
        )
    except AppException:
        raise


@router.put(
    "/supplier-qualification/{record_id}",
    summary="更新供应商资质记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_update_supplier_qualification(
    record_id: str,
    data: UpdateSupplierQualificationRequest,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["material_qa"],
    )
    try:
        result = await update_supplier_qualification_record(
            db, record_id, data.model_dump(exclude_unset=True, mode="json")
        )
        return success_response(
            data=SupplierQualificationOut.model_validate(result).model_dump(
                mode="json"
            ),
            message="更新成功",
        )
    except AppException:
        raise


@router.delete(
    "/supplier-qualification/{record_id}",
    summary="删除供应商资质记录（飞书）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_delete_supplier_qualification(
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["material_qa"],
    )
    try:
        await delete_supplier_qualification_record(db, record_id)
        return success_response(message="已删除")
    except AppException:
        raise


@router.post(
    "/supplier-qualification/pull",
    summary="拉取供应商资质记录（飞书->本地）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def api_pull_supplier_qualification(
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    try:
        result = await pull_supplier_qualification_records(db)
        return success_response(
            data=SupplierPullResult(**result).model_dump(mode="json"),
            message="拉取完成",
        )
    except AppException:
        raise


@router.get(
    "/statistics/suppliers",
    summary="获取供应商统计",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def api_get_supplier_statistics(
    current_user: CurrentUser = None, db: AsyncSession = Depends(get_db)
) -> Any:
    _require_user(current_user)
    stats = await get_supplier_statistics(db)
    return success_response(
        data=SupplierDashboardStatsOut(**stats).model_dump(mode="json")
    )
