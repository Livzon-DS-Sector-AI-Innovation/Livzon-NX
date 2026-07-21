"""测试 Regulatory Tracker 同步功能。

测试内容：
1. 同步第 1 页
2. 同步第 1-3 页

运行前确保：
- PostgreSQL 已启动
- alembic upgrade head 已执行
- seed 脚本已执行
"""

import asyncio
import logging
import sys
from app.platform.identity.models import User  # noqa: F401
import os

# 设置环境
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.core.database import async_session_factory
from app.modules.regulatory_tracker.models import (
    DataSource,
    DataChannel,
    RegulatoryDocument,
    SyncJob,
    SyncJobPage,
)
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.cde_crawler import CdeDomesticGuidelineAdapter
from app.modules.regulatory_tracker.services.sync_service import run_sync_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def check_prerequisites() -> tuple[DataSource, DataChannel] | None:
    """检查前置条件：数据库表存在、数据源和栏目已 seed"""
    async with async_session_factory() as db:
        # 检查表是否存在
        try:
            await db.execute(text("SELECT 1 FROM regulatory_tracker.data_sources LIMIT 1"))
        except Exception as e:
            logger.error(f"数据库表不存在或未创建: {e}")
            logger.error("请先执行: .venv/bin/alembic upgrade head")
            return None

        # 检查数据源
        source = await repo.get_data_source_by_code(db, "CDE")
        if not source:
            logger.error("CDE 数据源不存在，请先执行 seed:")
            logger.error("  .venv/bin/python scripts/seed_regulatory_tracker.py")
            return None

        # 检查栏目
        channel = await repo.get_channel_by_code(db, source.id, "cde_domestic_guideline")
        if not channel:
            logger.error("cde_domestic_guideline 栏目不存在，请先执行 seed")
            return None

        logger.info(f"✅ 数据源: {source.name} (id={source.id})")
        logger.info(f"✅ 栏目: {channel.name} (id={channel.id})")

        return source, channel


async def test_sync_page_1(source: DataSource, channel: DataChannel):
    """测试同步第 1 页"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 1: 同步第 1 页")
    logger.info("=" * 60)

    async with async_session_factory() as db:
        result = await run_sync_job(
            db=db,
            source=source,
            channel=channel,
            job_type="test",
            start_page=1,
            end_page=1,
            headless=True,
        )

        logger.info(f"结果: {result}")
        return result


async def test_sync_pages_1_3(source: DataSource, channel: DataChannel):
    """测试同步第 1-3 页"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: 同步第 1-3 页")
    logger.info("=" * 60)

    async with async_session_factory() as db:
        result = await run_sync_job(
            db=db,
            source=source,
            channel=channel,
            job_type="test",
            start_page=1,
            end_page=3,
            headless=True,
        )

        logger.info(f"结果: {result}")
        return result


async def show_db_stats():
    """显示数据库统计"""
    async with async_session_factory() as db:
        # 文档数量
        source = await repo.get_data_source_by_code(db, "CDE")
        channel = await repo.get_channel_by_code(db, source.id, "cde_domestic_guideline")
        doc_count = await repo.count_documents(db, source.id, channel.id)

        # 同步任务数量
        job_result = await db.execute(
            select(SyncJob).where(
                SyncJob.source_id == source.id,
                SyncJob.channel_id == channel.id,
            ).order_by(SyncJob.created_at.desc()).limit(5)
        )
        jobs = list(job_result.scalars().all())

        logger.info("\n" + "=" * 60)
        logger.info("数据库统计")
        logger.info("=" * 60)
        logger.info(f"法规文档总数: {doc_count}")
        logger.info(f"同步任务数: {len(jobs)}")

        for job in jobs:
            logger.info(
                f"  [{job.status}] {job.job_type} | "
                f"checked={job.checked_count} new={job.new_count} updated={job.updated_count} | "
                f"{job.started_at}"
            )

        # 显示前 5 条文档
        doc_result = await db.execute(
            select(RegulatoryDocument)
            .where(
                RegulatoryDocument.source_id == source.id,
                RegulatoryDocument.channel_id == channel.id,
            )
            .order_by(RegulatoryDocument.publish_date.desc())
            .limit(5)
        )
        docs = list(doc_result.scalars().all())

        if docs:
            logger.info(f"\n最新 {len(docs)} 条法规:")
            for doc in docs:
                logger.info(
                    f"  [{doc.publish_date}] {doc.title[:60]} | "
                    f"{doc.status_text} | {doc.classification}"
                )


async def main():
    logger.info("Regulatory Tracker 同步测试")
    logger.info("=" * 60)

    # 检查前置条件
    result = await check_prerequisites()
    if not result:
        return

    source, channel = result

    # 测试 1: 同步第 1 页
    result1 = await test_sync_page_1(source, channel)

    # 测试 2: 同步第 1-3 页
    result2 = await test_sync_pages_1_3(source, channel)

    # 显示数据库统计
    await show_db_stats()

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)
    logger.info(f"测试 1 (第 1 页): {'✅' if result1['status'] == 'success' else '❌'} "
                f"new={result1['new']} checked={result1['checked']}")
    logger.info(f"测试 2 (第 1-3 页): {'✅' if result2['status'] == 'success' else '❌'} "
                f"new={result2['new']} checked={result2['checked']}")


if __name__ == "__main__":
    asyncio.run(main())
