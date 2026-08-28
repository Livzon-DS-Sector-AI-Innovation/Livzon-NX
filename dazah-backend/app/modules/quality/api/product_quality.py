"""Product quality management API endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import error_response, paginated_response, success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.product_quality import ProductQualityRecord
from app.modules.quality.schemas.product_quality import (
    CreateProductQualityRequest,
    ProductQualityOut,
    UpdateProductQualityRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/product-quality",
    summary="获取产品质量列表",
    response_model=ApiResponseEnvelope[list[ProductQualityOut]],
)
async def list_product_quality(
    review_type: str | None = Query(None, description="评审类型"),
    status: str | None = Query(None, description="状态"),
    product_name: str | None = Query(None, description="产品名称"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(ProductQualityRecord).where(
            ProductQualityRecord.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(ProductQualityRecord)
            .where(ProductQualityRecord.is_deleted.is_(False))
        )

        filters = []
        if review_type:
            filters.append(ProductQualityRecord.review_type == review_type)
        if status:
            filters.append(ProductQualityRecord.status == status)
        if product_name:
            filters.append(ProductQualityRecord.product_name == product_name)
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters.append(
                or_(
                    ProductQualityRecord.record_code.ilike(pattern),
                    ProductQualityRecord.title.ilike(pattern),
                    ProductQualityRecord.conclusion.ilike(pattern),
                )
            )

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        base_query = (
            base_query.order_by(ProductQualityRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items_result = await db.execute(base_query)
        items = items_result.scalars().all()

        return paginated_response(
            data=[
                ProductQualityOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list product quality records")
        return error_response(message="获取列表失败，请稍后重试", status_code=500)


@router.get(
    "/product-quality/{record_id}",
    summary="获取产品质量详情",
    response_model=ApiResponseEnvelope[ProductQualityOut],
)
async def get_product_quality(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ProductQualityRecord).where(
                ProductQualityRecord.id == record_id,
                ProductQualityRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)
        return success_response(
            data=ProductQualityOut.model_validate(item).model_dump(mode="json")
        )
    except Exception:
        logger.exception("Failed to get product quality record")
        return error_response(message="获取详情失败，请稍后重试", status_code=500)


@router.post(
    "/product-quality",
    summary="创建产品质量记录",
    response_model=ApiResponseEnvelope[ProductQualityOut],
)
async def create_product_quality(
    data: CreateProductQualityRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        record = ProductQualityRecord(**data.model_dump())
        db.add(record)
        await db.flush()
        return success_response(
            data=ProductQualityOut.model_validate(record).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create product quality record")
        return error_response(message="创建失败，请稍后重试", status_code=400)


@router.put(
    "/product-quality/{record_id}",
    summary="更新产品质量记录",
    response_model=ApiResponseEnvelope[ProductQualityOut],
)
async def update_product_quality(
    record_id: uuid.UUID,
    data: UpdateProductQualityRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ProductQualityRecord).where(
                ProductQualityRecord.id == record_id,
                ProductQualityRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        result = await db.execute(
            select(ProductQualityRecord).where(ProductQualityRecord.id == record_id)
        )
        item = result.scalar_one()
        return success_response(
            data=ProductQualityOut.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update product quality record")
        return error_response(message="更新失败，请稍后重试", status_code=400)


@router.delete(
    "/product-quality/{record_id}",
    summary="删除产品质量记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_product_quality(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        result = await db.execute(
            select(ProductQualityRecord).where(
                ProductQualityRecord.id == record_id,
                ProductQualityRecord.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="记录不存在", status_code=404)

        item.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete product quality record")
        return error_response(message="删除失败，请稍后重试", status_code=500)
