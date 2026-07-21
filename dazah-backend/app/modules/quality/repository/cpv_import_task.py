"""CPV Import Task database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.cpv_import_task import CpvImportTask


async def create_import_task(db: AsyncSession, data: dict[str, Any]) -> CpvImportTask:
    """创建导入任务"""
    task = CpvImportTask(**data)
    db.add(task)
    await db.flush()
    return task


async def get_import_task_by_id(db: AsyncSession, task_id: uuid.UUID) -> CpvImportTask | None:
    """根据ID获取导入任务"""
    result = await db.execute(
        select(CpvImportTask).where(
            CpvImportTask.id == task_id,
            CpvImportTask.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_import_tasks(
    db: AsyncSession,
    product_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CpvImportTask], int]:
    """获取导入任务列表"""
    from sqlalchemy import func
    
    query = select(CpvImportTask).where(
        CpvImportTask.is_deleted == False  # noqa: E712
    )
    
    if product_id:
        query = query.where(CpvImportTask.product_id == product_id)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Paginate
    query = query.order_by(CpvImportTask.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tasks = list(result.scalars().all())
    
    return tasks, total


async def update_import_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    data: dict[str, Any],
) -> CpvImportTask | None:
    """更新导入任务"""
    task = await get_import_task_by_id(db, task_id)
    if not task:
        return None
    
    for key, value in data.items():
        setattr(task, key, value)
    
    await db.flush()
    return task
