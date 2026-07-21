"""Regulatory Tracker repository layer."""

import uuid
from datetime import datetime, date
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker.models import (
    DataSource,
    DataChannel,
    RegulatoryDocument,
    SyncJob,
    SyncJobPage,
)


# ============ DataSource ============

async def get_data_source_by_code(db: AsyncSession, code: str) -> DataSource | None:
    """根据编码获取数据源"""
    result = await db.execute(
        select(DataSource).where(
            DataSource.code == code,
            DataSource.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_data_source_by_id(db: AsyncSession, source_id: uuid.UUID) -> DataSource | None:
    """根据ID获取数据源"""
    result = await db.execute(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


# ============ DataChannel ============

async def get_channel_by_code(
    db: AsyncSession, source_id: uuid.UUID, code: str
) -> DataChannel | None:
    """根据编码获取栏目"""
    result = await db.execute(
        select(DataChannel).where(
            DataChannel.source_id == source_id,
            DataChannel.code == code,
            DataChannel.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_channel_by_id(db: AsyncSession, channel_id: uuid.UUID) -> DataChannel | None:
    """根据ID获取栏目"""
    result = await db.execute(
        select(DataChannel).where(
            DataChannel.id == channel_id,
            DataChannel.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


# ============ RegulatoryDocument ============

async def get_document_by_document_id(
    db: AsyncSession,
    source_id: uuid.UUID,
    channel_id: uuid.UUID,
    document_id: str,
) -> RegulatoryDocument | None:
    """根据 document_id 查询文档（去重键）"""
    result = await db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.source_id == source_id,
            RegulatoryDocument.channel_id == channel_id,
            RegulatoryDocument.document_id == document_id,
            RegulatoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def create_document(db: AsyncSession, data: dict[str, Any]) -> RegulatoryDocument:
    """创建新文档"""
    doc = RegulatoryDocument(**data)
    db.add(doc)
    await db.flush()
    return doc


async def update_document(
    db: AsyncSession, doc_id: uuid.UUID, data: dict[str, Any]
) -> RegulatoryDocument | None:
    """更新文档"""
    result = await db.execute(
        select(RegulatoryDocument).where(RegulatoryDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return None
    for key, value in data.items():
        if hasattr(doc, key):
            setattr(doc, key, value)
    await db.flush()
    return doc


async def count_documents(
    db: AsyncSession, source_id: uuid.UUID, channel_id: uuid.UUID
) -> int:
    """统计文档数量"""
    result = await db.execute(
        select(func.count(RegulatoryDocument.id)).where(
            RegulatoryDocument.source_id == source_id,
            RegulatoryDocument.channel_id == channel_id,
            RegulatoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar() or 0


# ============ SyncJob ============

async def create_sync_job(db: AsyncSession, data: dict[str, Any]) -> SyncJob:
    """创建同步任务"""
    job = SyncJob(**data)
    db.add(job)
    await db.flush()
    return job


async def get_sync_job_by_id(db: AsyncSession, job_id: uuid.UUID) -> SyncJob | None:
    """根据ID获取同步任务"""
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def update_sync_job(
    db: AsyncSession, job_id: uuid.UUID, data: dict[str, Any]
) -> SyncJob | None:
    """更新同步任务"""
    job = await get_sync_job_by_id(db, job_id)
    if not job:
        return None
    for key, value in data.items():
        if hasattr(job, key):
            setattr(job, key, value)
    await db.flush()
    return job


# ============ SyncJobPage ============

async def create_sync_job_page(db: AsyncSession, data: dict[str, Any]) -> SyncJobPage:
    """创建同步任务分页记录"""
    page = SyncJobPage(**data)
    db.add(page)
    await db.flush()
    return page


async def update_sync_job_page(
    db: AsyncSession, page_id: uuid.UUID, data: dict[str, Any]
) -> SyncJobPage | None:
    """更新同步任务分页记录"""
    result = await db.execute(
        select(SyncJobPage).where(SyncJobPage.id == page_id)
    )
    page = result.scalar_one_or_none()
    if not page:
        return None
    for key, value in data.items():
        if hasattr(page, key):
            setattr(page, key, value)
    await db.flush()
    return page


# ============ API 查询方法 ============

async def get_summary_stats(db: AsyncSession) -> dict[str, Any]:
    """获取统计摘要数据"""
    from datetime import date, timedelta
    
    # 总文档数
    total_result = await db.execute(
        select(func.count(RegulatoryDocument.id)).where(
            RegulatoryDocument.is_deleted == False  # noqa: E712
        )
    )
    total_count = total_result.scalar() or 0
    
    # 今日新增数
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_new_result = await db.execute(
        select(func.count(RegulatoryDocument.id)).where(
            RegulatoryDocument.is_deleted == False,  # noqa: E712
            RegulatoryDocument.first_found_at >= today_start
        )
    )
    today_new_count = today_new_result.scalar() or 0
    
    # 未读新增数
    unread_result = await db.execute(
        select(func.count(RegulatoryDocument.id)).where(
            RegulatoryDocument.is_deleted == False,  # noqa: E712
            RegulatoryDocument.is_new == True  # noqa: E712
        )
    )
    unread_new_count = unread_result.scalar() or 0
    
    # 最近同步任务
    last_sync_result = await db.execute(
        select(SyncJob)
        .where(SyncJob.finished_at.isnot(None))
        .order_by(SyncJob.finished_at.desc())
        .limit(1)
    )
    last_sync = last_sync_result.scalar_one_or_none()
    
    return {
        "totalCount": total_count,
        "todayNewCount": today_new_count,
        "unreadNewCount": unread_new_count,
        "lastSyncTime": last_sync.finished_at.isoformat() if last_sync and last_sync.finished_at else None,
        "lastSyncStatus": last_sync.status if last_sync else None,
    }


async def get_documents_with_filters(
    db: AsyncSession,
    keyword: str | None = None,
    publish_date_from: date | None = None,
    publish_date_to: date | None = None,
    status_text: str | None = None,
    classification: str | None = None,
    is_new: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RegulatoryDocument], int]:
    """带筛选条件的文档列表查询"""
    query = select(RegulatoryDocument).where(
        RegulatoryDocument.is_deleted == False  # noqa: E712
    )
    count_query = select(func.count(RegulatoryDocument.id)).where(
        RegulatoryDocument.is_deleted == False  # noqa: E712
    )
    
    # 应用筛选条件
    if keyword:
        keyword_filter = RegulatoryDocument.title.ilike(f"%{keyword}%")
        query = query.where(keyword_filter)
        count_query = count_query.where(keyword_filter)
    
    if publish_date_from:
        date_filter = RegulatoryDocument.publish_date >= publish_date_from
        query = query.where(date_filter)
        count_query = count_query.where(date_filter)
    
    if publish_date_to:
        date_filter = RegulatoryDocument.publish_date <= publish_date_to
        query = query.where(date_filter)
        count_query = count_query.where(date_filter)
    
    if status_text:
        status_filter = RegulatoryDocument.status_text == status_text
        query = query.where(status_filter)
        count_query = count_query.where(status_filter)
    
    if classification:
        class_filter = RegulatoryDocument.classification.ilike(f"%{classification}%")
        query = query.where(class_filter)
        count_query = count_query.where(class_filter)
    
    if is_new is not None:
        new_filter = RegulatoryDocument.is_new == is_new
        query = query.where(new_filter)
        count_query = count_query.where(new_filter)
    
    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    offset = (page - 1) * page_size
    query = query.order_by(RegulatoryDocument.publish_date.desc()).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    documents = list(result.scalars().all())
    
    return documents, total


async def get_document_by_id(db: AsyncSession, doc_id: uuid.UUID) -> RegulatoryDocument | None:
    """根据 ID 获取文档"""
    result = await db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.id == doc_id,
            RegulatoryDocument.is_deleted == False  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_sync_jobs_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SyncJob], int]:
    """获取同步任务列表"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(SyncJob.id))
    )
    total = count_result.scalar() or 0
    
    # 分页查询
    offset = (page - 1) * page_size
    result = await db.execute(
        select(SyncJob)
        .order_by(SyncJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    jobs = list(result.scalars().all())
    
    return jobs, total
