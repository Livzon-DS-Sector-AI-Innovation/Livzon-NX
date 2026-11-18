"""质量列表页附件缓存每日预热。

用户白天打开固体/液体/成品/物品/入库/领用等列表页时，附件直接命中本地缓存，
无需回源飞书。只预热镜像表可见行（page_key 即实体码，与前端请求三元组一致），
QC验证/成品异常列表量小且缩略图首次即快，不纳入预热。

预热走 get_attachment_thumbnail：一次调用同时缓存原图字节与缩略图。
失败（实体未配置/无下载权限）只记日志跳过，不影响可用性。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
    QualityItemsPageSnapshot,
)
from app.modules.quality.service.feishu_attachment_thumbnail import (
    get_attachment_thumbnail,
)
from app.platform.integrations.feishu.attachment_cache import (
    AttachmentCacheDiskError,
    get_attachment_cache,
)

logger = logging.getLogger(__name__)

_MAX_WARMUP_TOKENS = 2000
_WARMUP_CONCURRENCY = 2
_WARMUP_FETCH_ROWS = 128
# 单条回源超时（飞书慢/挂时不无限等待）；总预算必须低于 scheduler 的 300s
# 任务槽超时，超时即停止新预热、保留已缓存部分并返回统计。
_SINGLE_WARMUP_TIMEOUT_SECONDS = 60
_TOTAL_BUDGET_SECONDS = 240


def _extract_file_tokens(cells: object) -> list[str]:
    """从镜像行 cells 递归提取所有附件 file_token。"""
    tokens: list[str] = []

    def _walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                _walk(item)
        elif isinstance(value, dict):
            token = value.get("file_token")
            if token:
                tokens.append(str(token))
            for item in value.values():
                _walk(item)

    _walk(cells)
    return tokens


def _cron_to_time_of_day(expr: str) -> str:
    """cron "分 时 * * *" → scheduler FIXED_TIME 的 "HH:MM"。"""
    parts = expr.split()
    if len(parts) < 2:
        return "02:00"
    try:
        return f"{int(parts[1]):02d}:{int(parts[0]):02d}"
    except ValueError:
        return "02:00"


async def warmup_attachment_cache(
    max_tokens: int = _MAX_WARMUP_TOKENS,
) -> dict[str, int | bool]:
    """有界读取可见镜像行，并仅向磁盘预热附件。"""
    settings = get_settings()
    if (
        not settings.QUALITY_ATTACHMENT_WARMUP_ENABLED
        or not await get_attachment_cache().prepare_disk()
    ):
        return {
            "enabled": False,
            "collected": 0,
            "warmed": 0,
            "skipped": 0,
            "failed": 0,
            "timed_out": 0,
            "budget_hit": False,
        }

    targets: dict[tuple[str, str, str], None] = {}
    warmed = skipped = failed = timed_out = 0
    disk_failed = False

    async def collect_targets() -> None:
        if max_tokens <= 0:
            return
        stmt = (
            select(
                QualityItemsPageRow.source_record_id,
                QualityItemsPageRow.cells,
                QualityItemsPageSnapshot.page_key,
            )
            .join(
                QualityItemsPageSnapshot,
                QualityItemsPageSnapshot.id == QualityItemsPageRow.page_snapshot_id,
            )
            .where(
                QualityItemsPageSnapshot.is_deleted.is_(False),
                QualityItemsPageRow.is_deleted.is_(False),
            )
            .execution_options(yield_per=_WARMUP_FETCH_ROWS)
        )
        async with async_session_factory() as session:
            result = await session.stream(stmt)
            try:
                async for source_record_id, cells, page_key in result:
                    for token in _extract_file_tokens(cells):
                        targets[(page_key, source_record_id, token)] = None
                        if len(targets) >= max_tokens:
                            return
            finally:
                await result.close()

    async def _warm() -> None:
        nonlocal warmed, skipped, failed, timed_out, disk_failed
        while not disk_failed:
            target = next(pending, None)
            if target is None:
                return
            try:
                async with async_session_factory() as session:
                    async with asyncio.timeout(_SINGLE_WARMUP_TIMEOUT_SECONDS):
                        thumb = await get_attachment_thumbnail(
                            session, *target, disk_only=True
                        )
                if thumb is None:
                    skipped += 1
                else:
                    warmed += 1
            except AttachmentCacheDiskError:
                failed += 1
                disk_failed = True
            except AppException as exc:
                skipped += 1
                logger.debug("附件预热跳过: status=%s", exc.status_code)
            except TimeoutError:
                timed_out += 1
            except Exception as exc:
                failed += 1
                logger.debug("附件预热回源失败: %s", type(exc).__name__)

    budget_hit = False
    try:
        async with asyncio.timeout(_TOTAL_BUDGET_SECONDS):
            await collect_targets()
            pending = iter(targets)
            async with asyncio.TaskGroup() as workers:
                for _ in range(min(len(targets), _WARMUP_CONCURRENCY)):
                    workers.create_task(_warm())
    except TimeoutError:
        budget_hit = True
    logger.info(
        "附件预热结束: collected=%s warmed=%s skipped=%s failed=%s "
        "timed_out=%s budget_hit=%s disk_failed=%s",
        len(targets),
        warmed,
        skipped,
        failed,
        timed_out,
        budget_hit,
        disk_failed,
    )
    return {
        "enabled": True,
        "collected": len(targets),
        "warmed": warmed,
        "skipped": skipped,
        "failed": failed,
        "timed_out": timed_out,
        "budget_hit": budget_hit,
    }
