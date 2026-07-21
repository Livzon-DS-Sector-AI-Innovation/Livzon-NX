"""Product business workflows live here."""

import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.product.models import Product
from app.modules.product.repository import ProductRepository
from app.modules.product.schemas import ProductCreate, ProductUpdate, SyncStatusResponse
from app.platform.integrations.feishu.datasource import BitableDataSource

logger = logging.getLogger(__name__)


# ─── Feishu field mapping helpers ───


def _extract_text(value) -> str | None:
    """Extract text from Feishu array format or plain string."""
    if isinstance(value, list):
        texts = []
        for v in value:
            if isinstance(v, dict):
                t = v.get("text", "")
                if t:
                    texts.append(t)
            else:
                texts.append(str(v))
        return ", ".join(texts) if texts else None
    if isinstance(value, dict):
        if "text" in value:
            text = value["text"]
            return text if text else None
        if "value" in value and isinstance(value["value"], list):
            inner = value["value"]
            if len(inner) > 0 and isinstance(inner[0], dict):
                text = inner[0].get("text", "")
                return text if text else None
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _parse_feishu_record(record: dict) -> dict:
    """Convert a raw Feishu record into Product constructor kwargs."""
    fields = record.get("fields", {})
    rid = record.get("record_id", "")
    updated_time = record.get("updated_time", "")

    def gt(key: str):
        return fields.get(key)

    data = {
        "feishu_record_id": rid,
        "name": _extract_text(gt("产品名称")),
        "major_category": _extract_text(gt("产品代码")),
        "formulation_code": _extract_text(gt("制剂代码")),
        "product_type": _extract_text(gt("产品剂型")),
        "spec": _extract_text(gt("生产规格")),
        "capacity_range": _extract_text(gt("生产批量")),
        "unit": _extract_text(gt("单位")),
        "indication": _extract_text(gt("适应症")),
    }

    # Parse updated_time for sync tracking
    if updated_time:
        try:
            dt = datetime.fromisoformat(updated_time.replace("Z", "+00:00"))
            data["feishu_synced_at"] = dt.date()
        except Exception:
            data["feishu_synced_at"] = date.today()
    else:
        data["feishu_synced_at"] = date.today()

    # Remove empty strings for optional text fields to avoid overwriting
    cleaned = {
        k: v for k, v in data.items()
        if v is not None or k in ("feishu_record_id",)
    }
    return cleaned


# ─── Services ───


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ProductRepository(session)
        from app.core.config import get_settings

        settings = get_settings()
        self.bitable = BitableDataSource(
            app_token=settings.FEISHU_BITABLE_PRODUCT_APP_TOKEN,
            table_id=settings.FEISHU_BITABLE_PRODUCT_TABLE_ID,
        )

    async def get_product(self, product_id: UUID) -> Product:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise NotFoundException("产品", str(product_id))
        return product

    async def create_product(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        result = await self.repo.create(product)

        # Sync to Feishu
        try:
            rid = await self._sync_to_feishu(result)
            if rid:
                result.feishu_record_id = rid
                result.feishu_synced_at = date.today()
                await self.repo.update(result)
        except Exception as e:
            logger.warning("Feishu sync failed for product created: %s", e)

        return result

    async def update_product(self, product_id: UUID, data: ProductUpdate) -> Product:
        product = await self.get_product(product_id)
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(product, field, value)

        result = await self.repo.update(product)

        try:
            await self._sync_to_feishu(result)
        except Exception as e:
            logger.warning("Feishu sync failed for product updated: %s", e)

        return result

    async def delete_product(self, product_id: UUID) -> None:
        product = await self.get_product(product_id)
        await self.repo.soft_delete(product)

        # Delete from Feishu if linked
        try:
            if product.feishu_record_id:
                await self.bitable.delete(product.feishu_record_id)
        except Exception as e:
            logger.warning("Feishu sync failed for product deleted: %s", e)

    async def list_products(
        self,
        *,
        name: str | None = None,
        category: str | None = None,
        product_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]:
        return await self.repo.list_products(
            name=name,
            category=category,
            product_type=product_type,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

    # ─── Feishu sync ───

    async def sync_from_feishu(self) -> dict:
        """Pull all records from Feishu Bitable and upsert into local PG."""
        raw_records = await self.bitable.query(page_size=500)
        stats = {"created": 0, "updated": 0, "failed": 0, "total": len(raw_records)}

        for rec in raw_records:
            try:
                parsed = _parse_feishu_record(rec)
                if not parsed.get("name"):
                    stats["failed"] += 1
                    continue

                await self.repo.upsert_by_feishu_record(parsed)
                existing = await self.repo.get_by_feishu_record_id(
                    parsed["feishu_record_id"]
                )
                if existing and existing.created_at and (
                    datetime.utcnow() - existing.created_at.replace(tzinfo=None)
                ).total_seconds() < 60:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
            except Exception as e:
                import traceback
                logger.error(
                    "Failed to sync Feishu record %s: %s\n%s",
                    rec.get("record_id"),
                    e,
                    traceback.format_exc(),
                )
                stats["failed"] += 1

        return stats

    async def sync_to_feishu(self, product_id: UUID) -> str:
        """Force-sync a single product to Feishu."""
        product = await self.get_product(product_id)
        return await self._sync_to_feishu(product)

    async def get_sync_status(self) -> SyncStatusResponse:
        local_total = await self.repo.count_total()
        synced_count = await self.repo.count_synced()
        unsynced_count = local_total - synced_count

        try:
            feishu_items = await self.bitable.query(page_size=500)
            feishu_total = len(feishu_items)
        except Exception:
            feishu_total = 0

        return SyncStatusResponse(
            local_total=local_total,
            feishu_total=feishu_total,
            synced_count=synced_count,
            unsynced_count=unsynced_count,
            last_sync_at=None,
        )

    # ─── Internal helpers ───

    async def _sync_to_feishu(self, product: Product) -> str:
        """Sync one product to Feishu, creating or updating as needed."""
        fields: dict = {}
        if product.name:
            fields["产品名称"] = product.name
        if product.major_category:
            fields["产品代码"] = product.major_category
        if product.formulation_code:
            fields["制剂代码"] = product.formulation_code
        if product.product_type:
            fields["产品剂型"] = product.product_type
        if product.spec:
            fields["生产规格"] = product.spec
        if product.capacity_range:
            fields["生产批量"] = product.capacity_range
        if product.unit:
            fields["单位"] = product.unit
        if product.indication:
            fields["适应症"] = product.indication

        if product.feishu_record_id:
            await self.bitable.update(product.feishu_record_id, fields)
            return product.feishu_record_id
        else:
            rid = await self.bitable.create(fields)
            product.feishu_record_id = rid
            product.feishu_synced_at = date.today()
            await self.repo.update(product)
            return rid
