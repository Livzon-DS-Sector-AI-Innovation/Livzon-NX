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

logger = logging.getLogger(__name__)

_MAX_WARMUP_TOKENS = 2000
_WARMUP_CONCURRENCY = 5
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
    """预热全部镜像行附件到本地缓存（独立 session，适合后台任务直接调用）。"""
    settings = get_settings()
    if not settings.QUALITY_ATTACHMENT_WARMUP_ENABLED:
        return {
            "enabled": False,
            "collected": 0,
            "warmed": 0,
            "skipped": 0,
            "failed": 0,
            "timed_out": 0,
            "budget_hit": False,
        }

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(
                    QualityItemsPageRow.source_record_id,
                    QualityItemsPageRow.cells,
                    QualityItemsPageSnapshot.page_key,
                )
                .join(
                    QualityItemsPageSnapshot,
                    QualityItemsPageSnapshot.id
                    == QualityItemsPageRow.page_snapshot_id,
                )
                .where(QualityItemsPageSnapshot.is_deleted.is_(False))
            )
        ).all()

    targets: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source_record_id, cells, page_key in rows:
        for token in _extract_file_tokens(cells):
            key = (str(page_key), str(source_record_id), token)
            if key not in seen:
                seen.add(key)
                targets.append(key)
                if len(targets) >= max_tokens:
                    break
        if len(targets) >= max_tokens:
            break

    sem = asyncio.Semaphore(_WARMUP_CONCURRENCY)
    warmed = skipped = failed = timed_out = 0

    async def _warm(entity_code: str, record_id: str, file_token: str) -> None:
        nonlocal warmed, skipped, failed, timed_out
        async with sem:
            try:
                async with async_session_factory() as session:
                    await asyncio.wait_for(
                        get_attachment_thumbnail(
                            session, entity_code, record_id, file_token
                        ),
                        timeout=_SINGLE_WARMUP_TIMEOUT_SECONDS,
                    )
                warmed += 1
            except AppException as exc:
                skipped += 1
                logger.info(
                    "附件预热跳过 (%s/%s/%s): %s",
                    entity_code,
                    record_id,
                    file_token,
                    exc,
                )
            except TimeoutError:
                timed_out += 1
                logger.info(
                    "附件预热单条超时 (%s/%s/%s)",
                    entity_code,
                    record_id,
                    file_token,
                )
            except Exception:
                failed += 1
                logger.warning(
                    "附件预热失败 (%s/%s/%s)",
                    entity_code,
                    record_id,
                    file_token,
                    exc_info=True,
                )

    budget_hit = False
    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(_warm(*target) for target in targets),
                return_exceptions=True,
            ),
            timeout=_TOTAL_BUDGET_SECONDS,
        )
    except TimeoutError:
        budget_hit = True
        logger.info(
            "附件预热达到总预算 %ss，提前结束（预热 %s/跳过 %s/失败 %s/超时 %s）",
            _TOTAL_BUDGET_SECONDS,
            warmed,
            skipped,
            failed,
            timed_out,
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
