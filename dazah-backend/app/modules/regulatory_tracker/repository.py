"""Regulatory Tracker repository layer."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker.models import (
    DataChannel,
    DataSource,
    RegulatoryDocument,
    RegulatoryTrackerNotificationRecord,
    RegulatoryTrackerNotificationSetting,
    SyncJob,
    SyncJobPage,
)


@dataclass(slots=True, frozen=True)
class DocumentUpsertResult:
    """Result of repository-level document upsert."""

    document: RegulatoryDocument
    action: str


async def list_recent_accepted_document_ids(
    db: AsyncSession,
    *,
    threshold: date,
) -> list[uuid.UUID]:
    """返回 *threshold* 起（含）已接受且未删除的文档 id，按 capture_date 倒序。

    供 10:00 定时推送任务使用：capture_date 在夜间抓取时会刷新为当天，
    因此新增与更新的文档都会落在窗口内。
    """
    result = await db.execute(
        select(RegulatoryDocument.id)
        .where(
            RegulatoryDocument.is_deleted == False,  # noqa: E712
            RegulatoryDocument.filter_status == "accepted",
            RegulatoryDocument.capture_date >= threshold,
        )
        .order_by(RegulatoryDocument.capture_date.desc())
    )
    return list(result.scalars().all())


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


async def get_data_source_by_id(
    db: AsyncSession, source_id: uuid.UUID
) -> DataSource | None:
    """根据ID获取数据源"""
    result = await db.execute(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def create_data_source(db: AsyncSession, data: dict[str, Any]) -> DataSource:
    """创建数据源。"""
    source = DataSource(**data)
    db.add(source)
    await db.flush()
    return source


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


async def get_channel_by_id(
    db: AsyncSession, channel_id: uuid.UUID
) -> DataChannel | None:
    """根据ID获取栏目"""
    result = await db.execute(
        select(DataChannel).where(
            DataChannel.id == channel_id,
            DataChannel.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def create_data_channel(db: AsyncSession, data: dict[str, Any]) -> DataChannel:
    """创建栏目。"""
    channel = DataChannel(**data)
    db.add(channel)
    await db.flush()
    return channel


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
    return await get_document_by_id(db, doc_id)


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


async def get_document_by_unique_fields(
    db: AsyncSession,
    *,
    source_site_code: str | None,
    title: str,
    publish_date: date | None,
    source_url: str | None,
) -> RegulatoryDocument | None:
    """根据业务唯一键查询文档。"""
    query = select(RegulatoryDocument).where(
        RegulatoryDocument.source_site_code == source_site_code,
        RegulatoryDocument.title == title,
        RegulatoryDocument.publish_date == publish_date,
        RegulatoryDocument.is_deleted == False,  # noqa: E712
    )

    # EMA 列表里的 document URL 存在短期变化，不能再把 URL 作为唯一键的一部分，
    # 否则相同标题和发布日期会被重复写入多条记录。
    if source_site_code != "ema":
        query = query.where(RegulatoryDocument.source_url == source_url)

    result = await db.execute(
        query.order_by(
            RegulatoryDocument.capture_date.desc().nullslast(),
            RegulatoryDocument.created_at.desc(),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def get_document_by_source_channel_document_id(
    db: AsyncSession,
    *,
    source_id: uuid.UUID | None,
    channel_id: uuid.UUID | None,
    document_id: str | None,
) -> RegulatoryDocument | None:
    """按数据库唯一键 (source_id, channel_id, document_id) 查询文档。

    upsert 的业务键 miss 时兜底使用：EMA 等更新型报告发布/更新日期会变，
    业务键（含 publish_date）查不到既有记录，但唯一键字段稳定，可避免
    重复插入触发 uq_reg_docs_src_ch_doc 约束冲突。

    注意：**不按 is_deleted 过滤**——软删除行仍占用唯一约束，
    必须返回它以便 upsert 复活，否则插入仍会撞约束。
    """
    if source_id is None or channel_id is None or not document_id:
        return None
    result = await db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.source_id == source_id,
            RegulatoryDocument.channel_id == channel_id,
            RegulatoryDocument.document_id == document_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_document_by_unique_fields(
    db: AsyncSession,
    data: dict[str, Any],
) -> DocumentUpsertResult:
    """按业务唯一键执行文档 upsert。"""
    existing = await get_document_by_unique_fields(
        db,
        source_site_code=data.get("source_site_code"),
        title=data.get("title", ""),
        publish_date=data.get("publish_date"),
        source_url=data.get("source_url"),
    )

    # 业务键 miss 时按数据库唯一键兜底找回（EMA 更新型报告 publish_date 会变，
    # 但 source/channel/document_id 稳定），避免重复插入触发唯一约束冲突
    if existing is None:
        existing = await get_document_by_source_channel_document_id(
            db,
            source_id=data.get("source_id"),
            channel_id=data.get("channel_id"),
            document_id=data.get("document_id"),
        )

    if existing is None:
        document = await create_document(
            db,
            {
                **data,
                "content_hash": data.get("content_hash")
                or build_document_content_hash(data),
            },
        )
        return DocumentUpsertResult(document=document, action="inserted")

    content_fields = (
        "document_id",
        "status_text",
        "classification",
        "source_site_name",
        "version_text",
        "effective_date",
        # publish_date 是业务键的一部分，但 EMA 更新型记录靠唯一键兜底命中，
        # 日期刷新（如 last_updated_date 变化）需要随更新写入
        "publish_date",
        "summary_text",
        "capture_date",
        "filter_status",
        "filter_reason",
        "original_url",
        "content_hash",
        "raw_data",
    )

    update_data: dict[str, Any] = {}
    changed = False
    for field_name in content_fields:
        if field_name not in data:
            continue
        new_value = data[field_name]
        if getattr(existing, field_name) != new_value:
            update_data[field_name] = new_value
            changed = True

    if existing.is_new:
        update_data["is_new"] = False
    if existing.is_deleted:
        # 兜底查回的是软删行（仍然占用唯一约束），复活并保留本次内容
        update_data["is_deleted"] = False
    if data.get("last_checked_at") is not None:
        update_data["last_checked_at"] = data["last_checked_at"]

    if changed:
        update_data.update(
            {
                "ai_summary": None,
                "ai_key_points": None,
                "ai_relevance_score": None,
                "ai_analyzed_at": None,
                "ai_analysis_status": None,
            }
        )
        updated_doc = await update_document(db, existing.id, update_data)
        if updated_doc is None:
            raise RuntimeError(f"文档更新失败: {existing.id}")
        return DocumentUpsertResult(document=updated_doc, action="updated")

    if update_data:
        updated_doc = await update_document(db, existing.id, update_data)
        if updated_doc is None:
            raise RuntimeError(f"文档更新失败: {existing.id}")
        return DocumentUpsertResult(document=updated_doc, action="unchanged")

    return DocumentUpsertResult(document=existing, action="unchanged")


def build_document_content_hash(data: dict[str, Any]) -> str:
    """为文档内容生成稳定哈希。"""
    payload = {
        "title": data.get("title"),
        "publish_date": _serialize_hash_value(data.get("publish_date")),
        "status_text": data.get("status_text"),
        "classification": data.get("classification"),
        "source_site_code": data.get("source_site_code"),
        "source_site_name": data.get("source_site_name"),
        "source_url": data.get("source_url"),
        "version_text": data.get("version_text"),
        "effective_date": _serialize_hash_value(data.get("effective_date")),
        "summary_text": data.get("summary_text"),
        "filter_status": data.get("filter_status"),
        "filter_reason": data.get("filter_reason"),
        "original_url": data.get("original_url"),
        "raw_data": data.get("raw_data"),
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=_serialize_hash_value,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _serialize_hash_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# ============ SyncJob ============


async def create_sync_job(db: AsyncSession, data: dict[str, Any]) -> SyncJob:
    """创建同步任务"""
    job = SyncJob(**data)
    db.add(job)
    await db.flush()
    return job


async def get_sync_job_by_id(db: AsyncSession, job_id: uuid.UUID) -> SyncJob | None:
    """根据ID获取同步任务"""
    result = await db.execute(select(SyncJob).where(SyncJob.id == job_id))
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
    return await get_sync_job_by_id(db, job_id)


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
    result = await db.execute(select(SyncJobPage).where(SyncJobPage.id == page_id))
    page = result.scalar_one_or_none()
    if not page:
        return None
    for key, value in data.items():
        if hasattr(page, key):
            setattr(page, key, value)
    await db.flush()
    result = await db.execute(select(SyncJobPage).where(SyncJobPage.id == page_id))
    return result.scalar_one_or_none()


# ============ API 查询方法 ============


async def get_summary_stats(db: AsyncSession) -> dict[str, Any]:
    """获取统计摘要数据"""
    from datetime import date

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
            RegulatoryDocument.first_found_at >= today_start,
        )
    )
    today_new_count = today_new_result.scalar() or 0

    # 未读新增数
    unread_result = await db.execute(
        select(func.count(RegulatoryDocument.id)).where(
            RegulatoryDocument.is_deleted == False,  # noqa: E712
            RegulatoryDocument.is_new == True,  # noqa: E712
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
        "lastSyncTime": last_sync.finished_at.isoformat()
        if last_sync and last_sync.finished_at
        else None,
        "lastSyncStatus": last_sync.status if last_sync else None,
    }


async def get_documents_with_filters(
    db: AsyncSession,
    keyword: str | None = None,
    source_site: str | None = None,
    publish_date_from: date | None = None,
    publish_date_to: date | None = None,
    capture_date_from: date | None = None,
    capture_date_to: date | None = None,
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
        keyword_filter = (
            RegulatoryDocument.title.ilike(f"%{keyword}%")
            | RegulatoryDocument.version_text.ilike(f"%{keyword}%")
            | RegulatoryDocument.summary_text.ilike(f"%{keyword}%")
        )
        query = query.where(keyword_filter)
        count_query = count_query.where(keyword_filter)

    if source_site:
        site_filter = RegulatoryDocument.source_site_name == source_site
        query = query.where(site_filter)
        count_query = count_query.where(site_filter)

    if publish_date_from:
        date_filter = RegulatoryDocument.publish_date >= publish_date_from
        query = query.where(date_filter)
        count_query = count_query.where(date_filter)

    if publish_date_to:
        date_filter = RegulatoryDocument.publish_date <= publish_date_to
        query = query.where(date_filter)
        count_query = count_query.where(date_filter)

    if capture_date_from:
        capture_filter = RegulatoryDocument.capture_date >= capture_date_from
        query = query.where(capture_filter)
        count_query = count_query.where(capture_filter)

    if capture_date_to:
        capture_filter = RegulatoryDocument.capture_date <= capture_date_to
        query = query.where(capture_filter)
        count_query = count_query.where(capture_filter)

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
    query = (
        query.order_by(
            RegulatoryDocument.publish_date.desc().nullslast(),
            RegulatoryDocument.capture_date.desc().nullslast(),
            RegulatoryDocument.created_at.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(query)
    documents = list(result.scalars().all())

    return documents, total


async def get_document_by_id(
    db: AsyncSession, doc_id: uuid.UUID
) -> RegulatoryDocument | None:
    """根据 ID 获取文档"""
    result = await db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.id == doc_id,
            RegulatoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def list_documents_by_ids(
    db: AsyncSession,
    document_ids: list[uuid.UUID],
) -> list[RegulatoryDocument]:
    """按 ID 列表查询法规文档。"""
    if not document_ids:
        return []

    result = await db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.id.in_(document_ids),
            RegulatoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    documents = list(result.scalars().all())
    documents_by_id = {document.id: document for document in documents}
    return [
        documents_by_id[doc_id] for doc_id in document_ids if doc_id in documents_by_id
    ]


async def get_notification_setting(
    db: AsyncSession,
) -> RegulatoryTrackerNotificationSetting | None:
    """获取法规跟踪推送配置。"""
    result = await db.execute(
        select(RegulatoryTrackerNotificationSetting)
        .where(RegulatoryTrackerNotificationSetting.is_deleted == False)  # noqa: E712
        .order_by(RegulatoryTrackerNotificationSetting.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_notification_setting(
    db: AsyncSession,
    *,
    setting: RegulatoryTrackerNotificationSetting | None,
    is_enabled: bool,
    recent_days: int,
    recipient_open_id: str | None,
    recipient_name: str | None,
    recipient_department: str | None,
    schedule_time: str = "10:00",
) -> RegulatoryTrackerNotificationSetting:
    """创建或更新法规跟踪推送配置。"""
    if setting is None:
        setting = RegulatoryTrackerNotificationSetting(
            is_enabled=is_enabled,
            recent_days=recent_days,
            recipient_open_id=recipient_open_id,
            recipient_name=recipient_name,
            recipient_department=recipient_department,
            schedule_time=schedule_time,
        )
        db.add(setting)
        await db.flush()
        return setting

    setting.is_enabled = is_enabled
    setting.recent_days = recent_days
    setting.recipient_open_id = recipient_open_id
    setting.recipient_name = recipient_name
    setting.recipient_department = recipient_department
    setting.schedule_time = schedule_time
    await db.flush()
    return setting


async def notification_record_exists(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    recipient_open_id: str,
    content_hash: str | None,
) -> bool:
    """判断指定内容版本是否已经推送过。"""
    if not content_hash:
        return False

    result = await db.execute(
        select(RegulatoryTrackerNotificationRecord.id).where(
            RegulatoryTrackerNotificationRecord.document_id == document_id,
            RegulatoryTrackerNotificationRecord.recipient_open_id == recipient_open_id,
            RegulatoryTrackerNotificationRecord.content_hash == content_hash,
            RegulatoryTrackerNotificationRecord.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none() is not None


async def create_notification_records(
    db: AsyncSession,
    records: list[RegulatoryTrackerNotificationRecord],
) -> None:
    """批量创建法规推送记录。"""
    if not records:
        return

    db.add_all(records)
    await db.flush()


async def get_sync_jobs_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SyncJob], int]:
    """获取同步任务列表"""
    # 获取总数
    count_result = await db.execute(select(func.count(SyncJob.id)))
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
