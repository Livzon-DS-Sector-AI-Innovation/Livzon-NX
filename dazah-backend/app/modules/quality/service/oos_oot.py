"""Business rules for OOS/OOT lifecycle and OOT limit maintenance."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.quality.models.oos_oot import OosOotRecord
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct
from app.modules.quality.repository import oos_oot as repository


async def _get_record(db: AsyncSession, record_id: uuid.UUID) -> OosOotRecord:
    record = await repository.get_oos_oot_record(db, record_id)
    if record is None:
        raise NotFoundException("OOS/OOT记录", str(record_id))
    return record


async def list_oos_oot_records(
    db: AsyncSession,
    *,
    record_type: str | None,
    status: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[OosOotRecord], int]:
    return await repository.list_oos_oot_records(
        db,
        record_type=record_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


async def get_oos_oot_record(db: AsyncSession, record_id: uuid.UUID) -> OosOotRecord:
    return await _get_record(db, record_id)


async def create_oos_oot_record(
    db: AsyncSession, data: dict[str, object]
) -> OosOotRecord:
    record_code = str(data["record_code"]).strip()
    if await repository.get_oos_oot_record_by_code(db, record_code):
        raise DuplicateException("OOS/OOT记录编号", record_code)
    return await repository.create_oos_oot_record(
        db, {**data, "record_code": record_code, "status": "open"}
    )


async def update_oos_oot_record(
    db: AsyncSession, record_id: uuid.UUID, data: dict[str, object]
) -> OosOotRecord:
    record = await _get_record(db, record_id)
    if record.status == "closed":
        raise ValueError("已关闭的 OOS/OOT 记录不能编辑")
    return await repository.update_oos_oot_record(db, record, data)


async def start_oos_oot_investigation(
    db: AsyncSession, record_id: uuid.UUID
) -> OosOotRecord:
    record = await _get_record(db, record_id)
    if record.status == "closed":
        raise ValueError("已关闭的 OOS/OOT 记录不能重新启动调查")
    if record.status == "investigating":
        return record
    return await repository.update_oos_oot_record(
        db, record, {"status": "investigating"}
    )


async def close_oos_oot_record(
    db: AsyncSession,
    record_id: uuid.UUID,
    *,
    investigation_result: str,
    corrective_actions: str | None,
) -> OosOotRecord:
    record = await _get_record(db, record_id)
    if record.status != "investigating":
        raise ValueError("仅调查中的 OOS/OOT 记录可以关闭")
    return await repository.update_oos_oot_record(
        db,
        record,
        {
            "status": "closed",
            "investigation_result": investigation_result.strip(),
            "corrective_actions": corrective_actions,
            "closed_at": datetime.now(UTC),
        },
    )


async def delete_oos_oot_record(db: AsyncSession, record_id: uuid.UUID) -> None:
    await repository.soft_delete_oos_oot_record(db, await _get_record(db, record_id))


async def _get_product(db: AsyncSession, product_id: uuid.UUID) -> OotLimitProduct:
    product = await repository.get_oot_limit_product(db, product_id)
    if product is None:
        raise NotFoundException("OOT限度产品", str(product_id))
    return product


async def list_oot_limit_products(
    db: AsyncSession, *, keyword: str | None
) -> list[OotLimitProduct]:
    return await repository.list_oot_limit_products(db, keyword=keyword)


async def get_oot_limit_product(
    db: AsyncSession, product_id: uuid.UUID
) -> OotLimitProduct:
    return await _get_product(db, product_id)


async def create_oot_limit_product(
    db: AsyncSession, data: dict[str, object]
) -> OotLimitProduct:
    product_code = str(data["product_code"]).strip()
    if await repository.get_oot_limit_product_by_code(db, product_code):
        raise DuplicateException("OOT限度产品编码", product_code)
    return await repository.create_oot_limit_product(
        db, {**data, "product_code": product_code}
    )


async def update_oot_limit_product(
    db: AsyncSession, product_id: uuid.UUID, data: dict[str, object]
) -> OotLimitProduct:
    product = await _get_product(db, product_id)
    product_code = data.get("product_code")
    if product_code is not None:
        normalized_code = str(product_code).strip()
        if await repository.get_oot_limit_product_by_code(
            db, normalized_code, exclude_id=product_id
        ):
            raise DuplicateException("OOT限度产品编码", normalized_code)
        data = {**data, "product_code": normalized_code}
    return await repository.update_oot_limit_product(db, product, data)


async def delete_oot_limit_product(db: AsyncSession, product_id: uuid.UUID) -> None:
    product = await _get_product(db, product_id)
    for item in await repository.list_oot_limit_items(db, product.id):
        await repository.soft_delete_oot_limit_item(db, item)
    await repository.soft_delete_oot_limit_product(db, product)


async def _get_item(db: AsyncSession, item_id: uuid.UUID) -> OotLimitItem:
    item = await repository.get_oot_limit_item(db, item_id)
    if item is None:
        raise NotFoundException("OOT限度项目", str(item_id))
    return item


async def list_oot_limit_items(
    db: AsyncSession, product_id: uuid.UUID
) -> list[OotLimitItem]:
    await _get_product(db, product_id)
    return await repository.list_oot_limit_items(db, product_id)


async def create_oot_limit_item(
    db: AsyncSession, product_id: uuid.UUID, data: dict[str, object]
) -> OotLimitItem:
    await _get_product(db, product_id)
    raw_display_order = data.get("display_order", 1)
    display_order = int(str(raw_display_order))
    if await repository.get_oot_limit_item_by_order(db, product_id, display_order):
        raise DuplicateException("OOT限度项目显示顺序", str(display_order))
    return await repository.create_oot_limit_item(
        db, {**data, "product_id": product_id, "display_order": display_order}
    )


async def update_oot_limit_item(
    db: AsyncSession, item_id: uuid.UUID, data: dict[str, object]
) -> OotLimitItem:
    item = await _get_item(db, item_id)
    display_order = data.get("display_order")
    if display_order is not None and await repository.get_oot_limit_item_by_order(
        db, item.product_id, int(str(display_order)), exclude_id=item_id
    ):
        raise DuplicateException("OOT限度项目显示顺序", str(display_order))
    return await repository.update_oot_limit_item(db, item, data)


async def delete_oot_limit_item(db: AsyncSession, item_id: uuid.UUID) -> None:
    await repository.soft_delete_oot_limit_item(db, await _get_item(db, item_id))
