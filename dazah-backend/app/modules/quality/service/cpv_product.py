"""CPV Product service layer."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality import repository as repo
from app.modules.quality.models.cpv_product import CpvProduct
from app.modules.quality.schemas import CpvProductCreate, CpvProductUpdate


async def create_product(
    db: AsyncSession,
    data: CpvProductCreate,
) -> CpvProduct:
    """创建产品"""
    return await repo.create_product(db, data.model_dump())


async def get_product_by_id(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> CpvProduct:
    """获取产品"""
    product = await repo.get_product_by_id(db, product_id)
    if not product:
        raise NotFoundException("产品", str(product_id))
    return product


async def get_products(
    db: AsyncSession,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvProduct], int]:
    """获取产品列表"""
    return await repo.get_products(db, keyword, status, page, page_size)


async def update_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: CpvProductUpdate,
) -> CpvProduct:
    """更新产品"""
    product = await repo.update_product(
        db, product_id, data.model_dump(exclude_unset=True)
    )
    if not product:
        raise NotFoundException("产品", str(product_id))
    return product


async def delete_product(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> None:
    """删除产品"""
    success = await repo.delete_product(db, product_id)
    if not success:
        raise NotFoundException("产品", str(product_id))
