"""Product Quality Feishu API routes.

CRUD endpoints for product quality customer standards, directly operating on Feishu
Bitable.
Each product (霉酚酸、多拉菌素 etc.) is one entity under the "产品质量" group.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.quality.schemas.product_quality_standard import (
    ProductQualityStandardCreate,
    ProductQualityStandardUpdate,
)
from app.modules.quality.service.quality_feishu_pages_product_quality import (
    create_product_quality_record,
    delete_product_quality_record,
    get_product_quality_record,
    list_product_quality_records,
    pull_product_quality_records,
    update_product_quality_record,
)
from app.shared.schemas import ApiResponseEnvelope

router = APIRouter()

# 产品实体代码映射
PRODUCT_ENTITY_CODES = {
    "mfn": "product_quality_mfn",
    "dljs": "product_quality_dljs",
    "lftt": "product_quality_lftt",
    "mftt": "product_quality_mftt",
    "yslkms": "product_quality_yslkms",
    "bbas": "product_quality_bbas",
    "sas": "product_quality_sas",
}

PRODUCT_LABELS = {
    "mfn": "霉酚酸",
    "dljs": "多拉菌素",
    "lftt": "洛伐他汀",
    "mftt": "美伐他汀",
    "yslkms": "盐酸林可霉素",
    "bbas": "L-苯丙氨酸",
    "sas": "L-色氨酸",
}


# ============ Product Quality Standards ============


@router.get(
    "/product-quality-standards/{product_code}",
    summary="获取产品质量客户标准列表",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def list_product_quality_standards(
    product_code: str,
    keyword: str | None = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    result = await list_product_quality_records(
        db, entity_code, keyword=keyword, page=page, page_size=page_size
    )
    return success_response(
        data=result["items"],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.get(
    "/product-quality-standards/{product_code}/{record_id}",
    summary="获取产品质量客户标准详情",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def get_product_quality_standard(
    product_code: str,
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    record = await get_product_quality_record(db, entity_code, record_id)
    if not record:
        return success_response(data=None, message="记录不存在")
    return success_response(data=record)


@router.post(
    "/product-quality-standards/{product_code}",
    summary="创建产品质量客户标准记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def create_product_quality_standard(
    product_code: str,
    data: ProductQualityStandardCreate,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    record = await create_product_quality_record(
        db, entity_code, data.model_dump(exclude_unset=True)
    )
    return success_response(data=record, message="创建成功")


@router.put(
    "/product-quality-standards/{product_code}/{record_id}",
    summary="更新产品质量客户标准记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def update_product_quality_standard(
    product_code: str,
    record_id: str,
    data: ProductQualityStandardUpdate,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    record = await update_product_quality_record(
        db, entity_code, record_id, data.model_dump(exclude_unset=True)
    )
    return success_response(data=record, message="更新成功")


@router.delete(
    "/product-quality-standards/{product_code}/{record_id}",
    summary="删除产品质量客户标准记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_product_quality_standard(
    product_code: str,
    record_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    await delete_product_quality_record(db, entity_code, record_id)
    return success_response(data=None, message="删除成功")


@router.post(
    "/product-quality-standards/{product_code}/pull",
    summary="从飞书拉取产品质量客户标准",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def pull_product_quality_standards(
    product_code: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    entity_code = _resolve_product_entity(product_code)
    result = await pull_product_quality_records(db, entity_code)
    return success_response(data=result, message="拉取完成")


@router.get(
    "/product-quality-standards",
    summary="获取所有产品列表",
    response_model=ApiResponseEnvelope[list[dict[str, Any]]],
)
async def list_product_quality_products(
    current_user: CurrentUser = None,
) -> Any:
    """Return the list of available products for product quality standards."""
    if current_user is None:
        raise AppException(status_code=401, message="未授权，请先登录")
    items = [
        {"code": code, "label": label, "entity_code": PRODUCT_ENTITY_CODES[code]}
        for code, label in PRODUCT_LABELS.items()
    ]
    return success_response(data=items)


def _resolve_product_entity(product_code: str) -> str:
    entity_code = PRODUCT_ENTITY_CODES.get(product_code)
    if not entity_code:
        raise AppException(
            message=(
                f"无效的产品代码: {product_code}，"
                f"可选值: {list(PRODUCT_ENTITY_CODES.keys())}"
            )
        )
    return entity_code
