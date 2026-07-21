"""同步服务 - 处理采集数据入库逻辑。"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.cde_crawler import CdeDomesticGuidelineAdapter
from app.modules.regulatory_tracker.models import DataChannel, DataSource
from app.modules.regulatory_tracker.services.ai_analysis_service import analyze_and_update

logger = logging.getLogger(__name__)


async def upsert_document(
    db: AsyncSession,
    source_id: uuid.UUID,
    channel_id: uuid.UUID,
    normalized: dict[str, Any],
) -> tuple[str, uuid.UUID]:
    """插入或更新文档。

    Returns:
        ("created", doc_id) | ("updated", doc_id) | ("skipped", doc_id)
    """
    document_id = normalized["document_id"]
    if not document_id:
        return ("skipped", uuid.UUID(int=0))

    existing = await repo.get_document_by_document_id(db, source_id, channel_id, document_id)

    if existing:
        # 已存在：更新 last_checked_at，标记为非新文档
        await repo.update_document(db, existing.id, {
            "last_checked_at": datetime.now(timezone.utc),
            "is_new": False,
            "title": normalized.get("title", existing.title),
            "publish_date": normalized.get("publish_date") or existing.publish_date,
            "status_text": normalized.get("status_text", existing.status_text),
            "classification": normalized.get("classification", existing.classification),
            "raw_data": normalized.get("raw_data", existing.raw_data),
        })
        return ("updated", existing.id)

    # 不存在：新增
    doc = await repo.create_document(db, {
        "source_id": source_id,
        "channel_id": channel_id,
        "document_id": document_id,
        "title": normalized.get("title", ""),
        "publish_date": normalized.get("publish_date"),
        "status_text": normalized.get("status_text"),
        "classification": normalized.get("classification"),
        "original_url": normalized.get("original_url"),
        "raw_data": normalized.get("raw_data"),
        "is_new": True,
        "first_found_at": datetime.now(timezone.utc),
        "last_checked_at": datetime.now(timezone.utc),
    })
    return ("created", doc)


async def sync_page_to_db(
    db: AsyncSession,
    adapter: CdeDomesticGuidelineAdapter,
    source: DataSource,
    channel: DataChannel,
    job_id: uuid.UUID,
    page_num: int,
) -> dict[str, int]:
    """同步单页数据到数据库。

    Returns:
        {"checked": int, "new": int, "updated": int, "failed": int}
    """
    stats = {"checked": 0, "new": 0, "updated": 0, "failed": 0}

    # 记录分页开始
    page_record = await repo.create_sync_job_page(db, {
        "sync_job_id": job_id,
        "page_number": page_num,
        "page_size": 10,
        "total_records_on_page": 0,
        "new_records": 0,
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    })

    try:
        result = await adapter.sync_page(page_num)

        if not result.get("success"):
            await repo.update_sync_job_page(db, page_record.id, {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc),
                "error_message": result.get("error", "未知错误"),
            })
            return stats

        records = result.get("records", [])
        total_on_page = len(records)
        new_on_page = 0

        await repo.update_sync_job_page(db, page_record.id, {
            "total_records_on_page": total_on_page,
        })

        for record in records:
            stats["checked"] += 1
            try:
                normalized = adapter.normalize_record(record)
                action, result = await upsert_document(
                    db, source.id, channel.id, normalized
                )
                if action == "created":
                    stats["new"] += 1
                    new_on_page += 1
                    # Trigger AI analysis for new documents
                    try:
                        await analyze_and_update(db, result)
                    except Exception as e:
                        logger.error(f"AI 分析失败: {e}")
                elif action == "updated":
                    stats["updated"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"处理记录失败: {record.get('zdyzIdCODE', 'N/A')}: {e}")

        await repo.update_sync_job_page(db, page_record.id, {
            "new_records": new_on_page,
            "status": "synced",
            "finished_at": datetime.now(timezone.utc),
        })

    except Exception as e:
        logger.exception(f"同步第 {page_num} 页异常")
        await repo.update_sync_job_page(db, page_record.id, {
            "status": "failed",
            "finished_at": datetime.now(timezone.utc),
            "error_message": str(e),
        })

    return stats


async def run_sync_job(
    db: AsyncSession,
    source: DataSource,
    channel: DataChannel,
    job_type: str,
    start_page: int = 1,
    end_page: int | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """执行同步任务。

    Args:
        db: 数据库会话
        source: 数据源
        channel: 栏目
        job_type: 任务类型 (backfill/daily_sync/manual_sync/test)
        start_page: 起始页码
        end_page: 结束页码（None 表示全部）
        headless: 是否无头模式

    Returns:
        同步结果摘要
    """
    # 创建同步任务
    job = await repo.create_sync_job(db, {
        "source_id": source.id,
        "channel_id": channel.id,
        "job_type": job_type,
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    })

    total_stats = {"checked": 0, "new": 0, "updated": 0, "failed": 0}
    error_message = None

    try:
        async with CdeDomesticGuidelineAdapter(headless=headless) as adapter:
            # 如果 end_page 为 None，先获取总页数
            if end_page is None:
                total_pages = await adapter.get_total_pages()
                if total_pages is None:
                    raise RuntimeError("无法获取总页数")
                end_page = total_pages
                await repo.update_sync_job(db, job.id, {"total_pages": end_page})

            # 逐页同步
            for page_num in range(start_page, end_page + 1):
                logger.info(f"同步第 {page_num}/{end_page} 页...")
                stats = await sync_page_to_db(
                    db, adapter, source, channel, job.id, page_num
                )
                total_stats["checked"] += stats["checked"]
                total_stats["new"] += stats["new"]
                total_stats["updated"] += stats["updated"]
                total_stats["failed"] += stats["failed"]

                # 每页提交一次
                await db.commit()

        # 确定最终状态
        if total_stats["failed"] > 0 and total_stats["checked"] > 0:
            status = "partial_failed"
        elif total_stats["checked"] == 0:
            status = "failed"
            error_message = "未检查到任何记录"
        else:
            status = "success"

    except Exception as e:
        logger.exception("同步任务异常")
        status = "failed"
        error_message = str(e)

    # 更新任务状态
    await repo.update_sync_job(db, job.id, {
        "status": status,
        "finished_at": datetime.now(timezone.utc),
        "checked_count": total_stats["checked"],
        "new_count": total_stats["new"],
        "updated_count": total_stats["updated"],
        "error_message": error_message,
    })
    await db.commit()

    return {
        "job_id": str(job.id),
        "status": status,
        "checked": total_stats["checked"],
        "new": total_stats["new"],
        "updated": total_stats["updated"],
        "failed": total_stats["failed"],
        "error": error_message,
    }
