"""全量抓取 CDE 国内药品技术指导原则所有数据。

使用方法：
    python scripts/backfill_all.py

前置条件：
    1. 数据库已迁移：alembic upgrade head
    2. 种子数据已初始化：python scripts/seed_regulatory_tracker.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.platform.identity.models import User  # noqa: F401
from app.core.database import async_session_factory
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.models import DataChannel, DataSource
from app.modules.regulatory_tracker.services.sync_service import run_sync_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_all():
    """同步所有页面的历史数据。"""
    logger.info("=" * 60)
    logger.info("开始全量抓取 CDE 国内药品技术指导原则")
    logger.info("=" * 60)

    async with async_session_factory() as db:
        # 检查数据源
        source = await repo.get_data_source_by_code(db, "CDE")
        if not source:
            logger.error("❌ CDE 数据源不存在，请先执行：python scripts/seed_regulatory_tracker.py")
            return False

        channel = await repo.get_channel_by_code(db, source.id, "cde_domestic_guideline")
        if not channel:
            logger.error("❌ cde_domestic_guideline 栏目不存在，请先执行 seed")
            return False

        logger.info(f"✅ 数据源: {source.name}")
        logger.info(f"✅ 栏目: {channel.name}")

        # 检查是否已有数据
        doc_count = await repo.count_documents(db, source.id, channel.id)
        if doc_count > 0:
            logger.warning(f"⚠️  已存在 {doc_count} 条法规数据，是否继续？(y/n)")
            response = input()
            if response.lower() != 'y':
                logger.info("取消初始化")
                return False

        # 执行全量同步（end_page=None 表示同步所有页面）
        logger.info("开始全量同步（所有页面）...")
        result = await run_sync_job(
            db=db,
            source=source,
            channel=channel,
            job_type="backfill",
            start_page=1,
            end_page=None,  # None 表示同步所有页面
            headless=True,
        )

        logger.info("=" * 60)
        logger.info("全量抓取完成")
        logger.info("=" * 60)
        logger.info(f"状态: {result['status']}")
        logger.info(f"检查: {result['checked']} 条")
        logger.info(f"新增: {result['new']} 条")
        logger.info(f"更新: {result['updated']} 条")
        if result.get('error'):
            logger.error(f"错误: {result['error']}")

        return result['status'] == 'success'


if __name__ == "__main__":
    success = asyncio.run(backfill_all())
    sys.exit(0 if success else 1)
