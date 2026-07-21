"""Product data access layer."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.product.models import Product


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, product_id: UUID) -> Product | None:
        result = await self.session.execute(
            select(Product).where(
                Product.id == product_id,
                Product.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_record_id(self, record_id: str) -> Product | None:
        result = await self.session.execute(
            select(Product).where(
                Product.feishu_record_id == record_id,
                Product.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def update(self, product: Product) -> Product:
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def soft_delete(self, product: Product) -> None:
        product.is_deleted = True
        await self.session.commit()

    async def list_products(
        self,
        *,
        name: str | None = None,
        category: str | None = None,
        product_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Product], int]:
        base_query = select(Product).where(Product.is_deleted.is_(False))
        count_query = select(func.count(Product.id)).where(
            Product.is_deleted.is_(False)
        )

        if name:
            base_query = base_query.where(Product.name == name)
            count_query = count_query.where(Product.name == name)
        if category:
            base_query = base_query.where(Product.major_category == category)
            count_query = count_query.where(Product.major_category == category)
        if product_type:
            base_query = base_query.where(Product.product_type == product_type)
            count_query = count_query.where(Product.product_type == product_type)
        if keyword:
            like_pattern = f"%{keyword}%"
            base_query = base_query.where(
                (Product.name.ilike(like_pattern))
                | (Product.spec.ilike(like_pattern))
                | (Product.formulation_code.ilike(like_pattern))
            )
            count_query = count_query.where(
                (Product.name.ilike(like_pattern))
                | (Product.spec.ilike(like_pattern))
                | (Product.formulation_code.ilike(like_pattern))
            )

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        if sort_order.lower() == "desc":
            base_query = base_query.order_by(getattr(Product, sort_by).desc())
        else:
            base_query = base_query.order_by(getattr(Product, sort_by).asc())

        base_query = base_query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(base_query)
        return list(result.scalars().all()), total

    async def upsert_by_feishu_record(self, data: dict) -> None:
        """Upsert a product by feishu_record_id."""
        record_id = data.get("feishu_record_id")
        if not record_id:
            return

        existing = await self.get_by_feishu_record_id(record_id)
        if existing:
            for key, value in data.items():
                if key != "id" and value is not None:
                    setattr(existing, key, value)
            await self.update(existing)
        else:
            product = Product(**data)
            await self.create(product)

    async def count_total(self) -> int:
        result = await self.session.execute(
            select(func.count(Product.id)).where(Product.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def count_synced(self) -> int:
        result = await self.session.execute(
            select(func.count(Product.id)).where(
                Product.is_deleted.is_(False),
                Product.feishu_record_id.isnot(None),
            )
        )
        return result.scalar() or 0
