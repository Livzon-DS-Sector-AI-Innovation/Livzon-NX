"""CPV Product database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.cpv_product import CpvProduct


async def create_product(db: AsyncSession, data: dict[str, Any]) -> CpvProduct:
    """创建产品"""
    product = CpvProduct(**data)
    db.add(product)
    await db.flush()
    return product


async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> CpvProduct | None:
    """根据ID获取产品"""
    result = await db.execute(
        select(CpvProduct).where(
            CpvProduct.id == product_id,
            CpvProduct.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_products(
    db: AsyncSession,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvProduct], int]:
    """获取产品列表"""
    query = select(CpvProduct).where(CpvProduct.is_deleted == False)  # noqa: E712
    
    if keyword:
        query = query.where(CpvProduct.name.ilike(f"%{keyword}%"))
    if status:
        query = query.where(CpvProduct.status == status)
    
    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Paginate
    query = query.order_by(CpvProduct.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    products = list(result.scalars().all())
    
    return products, total


async def update_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: dict[str, Any],
) -> CpvProduct | None:
    """更新产品"""
    product = await get_product_by_id(db, product_id)
    if not product:
        return None
    
    for key, value in data.items():
        setattr(product, key, value)
    
    await db.flush()
    return product


async def delete_product(db: AsyncSession, product_id: uuid.UUID) -> bool:
    """删除产品（软删除）"""
    product = await get_product_by_id(db, product_id)
    if not product:
        return False
    
    product.is_deleted = True
    await db.flush()
    return True
