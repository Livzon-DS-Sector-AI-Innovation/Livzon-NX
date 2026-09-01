"""OOT limit management API endpoints."""

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
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct
from app.modules.quality.schemas.oot_limit import (
    CreateOotLimitItemRequest,
    CreateOotLimitProductRequest,
    OotLimitItemOut,
    OotLimitProductOut,
    UpdateOotLimitItemRequest,
    UpdateOotLimitProductRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oos-oot")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/oot-limit-products",
    summary="获取OOT限度产品列表",
    response_model=ApiResponseEnvelope[list[OotLimitProductOut]],
)
async def list_oot_limit_products(
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(OotLimitProduct).where(
            OotLimitProduct.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(OotLimitProduct)
            .where(OotLimitProduct.is_deleted.is_(False))
        )

        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters = or_(
                OotLimitProduct.product_code.ilike(pattern),
                OotLimitProduct.product_name.ilike(pattern),
                OotLimitProduct.document_title.ilike(pattern),
                OotLimitProduct.version_label.ilike(pattern),
            )
            base_query = base_query.where(filters)
            count_query = count_query.where(filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        result = await db.execute(
            base_query.order_by(OotLimitProduct.product_code.asc())
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()
        return paginated_response(
            data=[
                OotLimitProductOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list OOT limit products")
        return error_response(message="操作失败，请稍后重试", status_code=500)


@router.post(
    "/oot-limit-products",
    summary="创建OOT限度产品",
    response_model=ApiResponseEnvelope[OotLimitProductOut],
)
async def create_oot_limit_product(
    data: CreateOotLimitProductRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        product = OotLimitProduct(**data.model_dump())
        db.add(product)
        await db.flush()
        result = await db.execute(
            select(OotLimitProduct).where(OotLimitProduct.id == product.id)
        )
        product = result.scalar_one()
        return success_response(
            data=OotLimitProductOut.model_validate(product).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create OOT limit product")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


@router.put(
    "/oot-limit-products/{product_id}",
    summary="更新OOT限度产品",
    response_model=ApiResponseEnvelope[OotLimitProductOut],
)
async def update_oot_limit_product(
    product_id: uuid.UUID,
    data: UpdateOotLimitProductRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(OotLimitProduct).where(
                OotLimitProduct.id == product_id,
                OotLimitProduct.is_deleted.is_(False),
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            return error_response(message="产品不存在", status_code=404)

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(product, key, value)

        await db.flush()
        result = await db.execute(
            select(OotLimitProduct).where(OotLimitProduct.id == product.id)
        )
        product = result.scalar_one()
        return success_response(
            data=OotLimitProductOut.model_validate(product).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update OOT limit product")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


@router.delete(
    "/oot-limit-products/{product_id}",
    summary="删除OOT限度产品",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_oot_limit_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(OotLimitProduct).where(
                OotLimitProduct.id == product_id,
                OotLimitProduct.is_deleted.is_(False),
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            return error_response(message="产品不存在", status_code=404)

        product.is_deleted = True
        item_result = await db.execute(
            select(OotLimitItem).where(
                OotLimitItem.product_id == product_id,
                OotLimitItem.is_deleted.is_(False),
            )
        )
        for item in item_result.scalars().all():
            item.is_deleted = True

        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete OOT limit product")
        return error_response(message="操作失败，请稍后重试", status_code=500)


@router.get(
    "/oot-limit-items",
    summary="获取OOT限度明细列表",
    response_model=ApiResponseEnvelope[list[OotLimitItemOut]],
)
async def list_oot_limit_items(
    product_id: uuid.UUID = Query(..., description="产品ID"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        base_query = select(OotLimitItem).where(
            OotLimitItem.product_id == product_id,
            OotLimitItem.is_deleted.is_(False),
        )
        count_query = (
            select(func.count())
            .select_from(OotLimitItem)
            .where(
                OotLimitItem.product_id == product_id,
                OotLimitItem.is_deleted.is_(False),
            )
        )

        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            filters = or_(
                OotLimitItem.item_group.ilike(pattern),
                OotLimitItem.item_name.ilike(pattern),
                OotLimitItem.standard_value.ilike(pattern),
                OotLimitItem.oot_limit_value.ilike(pattern),
                OotLimitItem.remark.ilike(pattern),
            )
            base_query = base_query.where(filters)
            count_query = count_query.where(filters)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        result = await db.execute(
            base_query.order_by(OotLimitItem.display_order.asc())
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()
        return paginated_response(
            data=[
                OotLimitItemOut.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception:
        logger.exception("Failed to list OOT limit items")
        return error_response(message="操作失败，请稍后重试", status_code=500)


@router.post(
    "/oot-limit-items",
    summary="创建OOT限度明细",
    response_model=ApiResponseEnvelope[OotLimitItemOut],
)
async def create_oot_limit_item(
    data: CreateOotLimitItemRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    try:
        product_result = await db.execute(
            select(OotLimitProduct).where(
                OotLimitProduct.id == data.product_id,
                OotLimitProduct.is_deleted.is_(False),
            )
        )
        product = product_result.scalar_one_or_none()
        if product is None:
            return error_response(message="产品不存在", status_code=404)

        item = OotLimitItem(**data.model_dump())
        db.add(item)
        await db.flush()
        result = await db.execute(
            select(OotLimitItem).where(OotLimitItem.id == item.id)
        )
        item = result.scalar_one()
        return success_response(
            data=OotLimitItemOut.model_validate(item).model_dump(mode="json"),
            message="创建成功",
        )
    except Exception:
        logger.exception("Failed to create OOT limit item")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


@router.put(
    "/oot-limit-items/{item_id}",
    summary="更新OOT限度明细",
    response_model=ApiResponseEnvelope[OotLimitItemOut],
)
async def update_oot_limit_item(
    item_id: uuid.UUID,
    data: UpdateOotLimitItemRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(OotLimitItem).where(
                OotLimitItem.id == item_id,
                OotLimitItem.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="明细不存在", status_code=404)

        update_data = data.model_dump(exclude_unset=True)
        if "product_id" in update_data:
            product_result = await db.execute(
                select(OotLimitProduct).where(
                    OotLimitProduct.id == update_data["product_id"],
                    OotLimitProduct.is_deleted.is_(False),
                )
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                return error_response(message="产品不存在", status_code=404)

        for key, value in update_data.items():
            setattr(item, key, value)

        await db.flush()
        result = await db.execute(
            select(OotLimitItem).where(OotLimitItem.id == item.id)
        )
        item = result.scalar_one()
        return success_response(
            data=OotLimitItemOut.model_validate(item).model_dump(mode="json"),
            message="更新成功",
        )
    except Exception:
        logger.exception("Failed to update OOT limit item")
        return error_response(message="请求处理失败，请检查输入后重试", status_code=400)


@router.delete(
    "/oot-limit-items/{item_id}",
    summary="删除OOT限度明细",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_oot_limit_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    try:
        result = await db.execute(
            select(OotLimitItem).where(
                OotLimitItem.id == item_id,
                OotLimitItem.is_deleted.is_(False),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return error_response(message="明细不存在", status_code=404)

        item.is_deleted = True
        await db.flush()
        return success_response(message="已删除")
    except Exception:
        logger.exception("Failed to delete OOT limit item")
        return error_response(message="操作失败，请稍后重试", status_code=500)
