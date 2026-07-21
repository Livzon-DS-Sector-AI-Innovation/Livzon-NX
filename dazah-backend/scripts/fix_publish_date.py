"""修复 publish_date 为空的记录。

利用已有的 raw_data.issueDate 回填 publish_date。
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from app.platform.identity.models import User  # noqa: F401
from app.core.database import async_session_factory
from app.modules.regulatory_tracker.models import RegulatoryDocument

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def fix_publish_date():
    """修复 publish_date 为空的记录。"""
    logger.info("=" * 60)
    logger.info("开始修复 publish_date 为空的记录")
    logger.info("=" * 60)

    async with async_session_factory() as db:
        # 统计修复前数据
        total_result = await db.execute(
            select(func.count(RegulatoryDocument.id))
        )
        total_count = total_result.scalar()

        no_date_result = await db.execute(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.publish_date.is_(None)
            )
        )
        no_date_count = no_date_result.scalar()

        logger.info(f"修复前 - 总记录数: {total_count}")
        logger.info(f"修复前 - publish_date 为空: {no_date_count}")

        # 查询所有 publish_date 为空的记录
        result = await db.execute(
            select(RegulatoryDocument).where(
                RegulatoryDocument.publish_date.is_(None)
            )
        )
        docs = result.scalars().all()

        fixed_count = 0
        failed_count = 0

        for doc in docs:
            raw_data = doc.raw_data or {}
            issue_date_str = raw_data.get("issueDate", "").strip()

            if not issue_date_str:
                logger.warning(f"文档 {doc.document_id} 的 raw_data 中没有 issueDate")
                failed_count += 1
                continue

            # 尝试解析日期
            publish_date = None
            if len(issue_date_str) == 8:
                try:
                    publish_date = datetime.strptime(issue_date_str, "%Y%m%d").date()
                except ValueError as e:
                    logger.warning(f"文档 {doc.document_id} 日期解析失败: {issue_date_str}, 错误: {e}")
                    failed_count += 1
                    continue
            else:
                logger.warning(f"文档 {doc.document_id} 日期格式错误: {issue_date_str} (长度: {len(issue_date_str)})")
                failed_count += 1
                continue

            # 更新 publish_date
            doc.publish_date = publish_date
            fixed_count += 1
            logger.info(f"✅ 修复文档 {doc.document_id}: publish_date = {publish_date}")

        await db.commit()

        # 统计修复后数据
        total_result_after = await db.execute(
            select(func.count(RegulatoryDocument.id))
        )
        total_count_after = total_result_after.scalar()

        no_date_result_after = await db.execute(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.publish_date.is_(None)
            )
        )
        no_date_count_after = no_date_result_after.scalar()

        has_date_count_after = total_count_after - no_date_count_after

        logger.info("=" * 60)
        logger.info("修复完成")
        logger.info("=" * 60)
        logger.info(f"总记录数: {total_count_after}")
        logger.info(f"publish_date 非空数量: {has_date_count_after}")
        logger.info(f"publish_date 为空数量: {no_date_count_after}")
        logger.info(f"成功修复: {fixed_count}")
        logger.info(f"修复失败: {failed_count}")


if __name__ == "__main__":
    asyncio.run(fix_publish_date())
