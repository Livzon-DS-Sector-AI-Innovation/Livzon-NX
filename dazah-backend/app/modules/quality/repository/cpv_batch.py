"""CPV Batch database queries."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.quality.models.cpv_batch import CpvBatch


async def create_batch(db: AsyncSession, data: dict[str, Any]) -> CpvBatch:
    """创建批次"""
    batch = CpvBatch(**data)
    db.add(batch)
    await db.flush()
    return batch


async def get_batch_by_id(db: AsyncSession, batch_id: uuid.UUID) -> CpvBatch | None:
    """根据ID获取批次"""
    result = await db.execute(
        select(CpvBatch).where(
            CpvBatch.id == batch_id,
            CpvBatch.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_batch_by_no(
    db: AsyncSession,
    product_id: uuid.UUID,
    batch_no: str,
    data_type: str,
) -> CpvBatch | None:
    """根据批号获取批次"""
    result = await db.execute(
        select(CpvBatch).where(
            CpvBatch.product_id == product_id,
            CpvBatch.batch_no == batch_no,
            CpvBatch.data_type == data_type,
            CpvBatch.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_batches(
    db: AsyncSession,
    product_id: uuid.UUID,
    data_type: str | None = None,
    batch_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvBatch], int]:
    """获取批次列表"""
    from sqlalchemy import func
    
    query = select(CpvBatch).where(
        CpvBatch.product_id == product_id,
        CpvBatch.is_deleted == False,  # noqa: E712
    )
    
    if data_type:
        query = query.where(CpvBatch.data_type == data_type)
    if batch_no:
        query = query.where(CpvBatch.batch_no.ilike(f"%{batch_no}%"))
    if start_date:
        query = query.where(CpvBatch.production_date >= start_date)
    if end_date:
        query = query.where(CpvBatch.production_date <= end_date)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Paginate
    query = query.order_by(CpvBatch.production_date.desc(), CpvBatch.batch_no)
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    batches = list(result.scalars().all())
    
    return batches, total




async def count_batches(
    db: AsyncSession,
    product_id: uuid.UUID,
    data_type: str | None = None,
) -> int:
    """统计批次数量（不分页）"""
    from sqlalchemy import func
    
    query = select(func.count()).where(
        CpvBatch.product_id == product_id,
        CpvBatch.is_deleted == False,  # noqa: E712
    )
    if data_type:
        query = query.where(CpvBatch.data_type == data_type)
    
    result = await db.execute(query)
    return result.scalar_one()

async def delete_batches_by_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    data_type: str,
) -> int:
    """删除产品下某类型的所有批次（软删除）"""
    from sqlalchemy import update
    
    result = await db.execute(
        update(CpvBatch)
        .where(
            CpvBatch.product_id == product_id,
            CpvBatch.data_type == data_type,
            CpvBatch.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True)
    )
    return result.rowcount
