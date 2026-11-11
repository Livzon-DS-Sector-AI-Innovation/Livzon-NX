"""Administration scheduled tasks.

烟酒礼品管理的飞书只读镜像需要比每日全量更及时（领用申请随时经飞书表单
提交），因此每 15 分钟同步一次所有已发现的数据表。只读拉取，不向飞书外发消息。
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.administration.repository import AdministrationRepository
from app.modules.administration.service import (
    build_read_mirror_service,
    prune_resource_history,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger("dazah.administration.scheduler")

READ_MIRROR_SYNC_INTERVAL = timedelta(minutes=15)
#: 完成时间必然晚于触发时间几秒，阈值留出余量，否则每轮都要多等一个周期。
READ_MIRROR_SYNC_MARGIN = timedelta(minutes=13)


class AdministrationFeishuReadSyncGenerator(TaskGenerator):
    """每 15 分钟刷新行政模块飞书只读镜像。"""

    name = "administration.feishu_read_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=int(READ_MIRROR_SYNC_INTERVAL.total_seconds()),
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 30 * 60
    enabled = True
    settings_toggle_key = ""

    async def find_due(self, session: AsyncSession) -> list[str]:
        repo = AdministrationRepository(session)
        # is_active = 「启用自动同步」开关；页面读取与手动同步不受它限制。
        config = await repo.get_active_config()
        if config is None or not config.app_id or not config.encrypted_app_secret:
            return []
        threshold = datetime.now(UTC) - READ_MIRROR_SYNC_MARGIN
        # 并发保护由平台同步服务的 Redis 锁负责（撞锁返回 409，下一轮再试），
        # 这里不再按 sync_status 过滤，避免进程中断留下的 running 卡死同步。
        return [
            str(item.id)
            for item in await repo.list_syncable_resources()
            if item.last_complete_sync_at is None
            or item.last_complete_sync_at < threshold
        ]

    async def execute_one(self, session: AsyncSession, item: Any) -> None:
        resource_id = UUID(str(item))
        try:
            service = await build_read_mirror_service(session)
            await service.sync_resource(resource_id)
        except AppException as exc:
            # 凭证未配置、或同一数据表已在同步（409）属于可预期状态，下一轮再试。
            logger.info("administration feishu read sync skipped: %s", exc.message)
            return
        try:
            await prune_resource_history(session, resource_id)
        except Exception:
            logger.exception(
                "administration feishu mirror prune failed: resource=%s", resource_id
            )
