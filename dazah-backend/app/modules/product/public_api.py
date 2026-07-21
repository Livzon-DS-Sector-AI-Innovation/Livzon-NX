"""Product module public API exports."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.product.repository import ProductRepository
from app.modules.product.schemas import ProductResponse


async def get_product_by_id(session: AsyncSession, product_id: UUID) -> ProductResponse | None:
    repo = ProductRepository(session)
    product = await repo.get_by_id(product_id)
    if product:
        return ProductResponse.model_validate(product)
    return None


async def list_all_product_names(session: AsyncSession) -> list[dict]:
    repo = ProductRepository(session)
    products, _ = await repo.list_products(page=1, page_size=1000)
    return [{"id": str(p.id), "name": p.name, "spec": p.spec} for p in products]
