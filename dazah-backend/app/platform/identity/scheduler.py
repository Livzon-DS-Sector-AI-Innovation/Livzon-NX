"""Identity module scheduled tasks."""

import asyncio
import logging
from datetime import datetime, timedelta

from app.core.config import get_settings

logger = logging.getLogger(__name__)

stop_member_sync_flag = asyncio.Event()


async def member_sync_loop() -> None:
    """每天 00:00 同步 FEISHU_SYNC_MEMBER_DEPT_ID 下的成员"""
    settings = get_settings()
    target = settings.FEISHU_SYNC_MEMBER_DEPT_ID
    if not target:
        logger.info(
            "飞书成员同步未配置（FEISHU_SYNC_MEMBER_DEPT_ID 为空），跳过启动"
        )
        return

    logger.info("飞书成员同步任务已启动（每天 00:00，target=%s）", target)

    while not stop_member_sync_flag.is_set():
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        wait_seconds = (next_midnight - now).total_seconds()
        logger.info(
            "下次成员同步将在 %.0f 分钟后",
            wait_seconds / 60,
        )
        try:
            await asyncio.wait_for(
                stop_member_sync_flag.wait(), timeout=wait_seconds,
            )
            break
        except TimeoutError:
            pass

        if not stop_member_sync_flag.is_set() and target:
            try:
                from app.platform.integrations.feishu.sync import sync_members
                await sync_members(target)
            except Exception:
                logger.exception("Member sync failed")

    logger.info("飞书成员同步任务已停止")
