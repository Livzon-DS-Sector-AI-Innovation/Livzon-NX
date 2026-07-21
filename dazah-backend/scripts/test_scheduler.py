"""测试 scheduler 的 daily_sync_job 可以正确执行。"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.platform.identity.models import User  # noqa: F401
from app.core.database import async_session_factory
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.tasks.sync_tasks import daily_sync_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("测试 scheduler daily_sync_job")
    logger.info("=" * 60)

    # 执行一次同步
    await daily_sync_job()

    # 检查结果
    async with async_session_factory() as db:
        source = await repo.get_data_source_by_code(db, "CDE")
        if not source:
            logger.error("CDE 数据源不存在")
            return

        channel = await repo.get_channel_by_code(db, source.id, "cde_domestic_guideline")
        if not channel:
            logger.error("栏目不存在")
            return

        doc_count = await repo.count_documents(db, source.id, channel.id)
        logger.info("法规文档总数: %d", doc_count)

        stats = await repo.get_summary_stats(db)
        logger.info("统计摘要: %s", stats)

    logger.info("✅ 测试完成")


if __name__ == "__main__":
    asyncio.run(main())
