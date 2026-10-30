"""事件驱动的镜像页即时刷新。

飞书多维表格「记录变更」事件（bitable_handler 分发）命中镜像页绑定的表时，
去抖后立即同步该页镜像（特殊危险作业页同步后再自动转录台账），页面数据
秒级跟上飞书，不再等待 15 分钟定时轮询。

并发与重入策略：

- 去抖：短时间多次变更合并为一次同步（防抖等待期的新事件只重置计时）；
- 单页串行：某页同步进行中收到新事件 → 标记 rerun，本轮完成后自动补跑；
- 撞锁退避：与定时轮询撞上 Redis 锁（409）时按间隔退避重试，定时同步
  完成后本次变更自然可见；
- 定时轮询保留作为兜底，事件链路故障不影响最终一致。
"""

from __future__ import annotations

import asyncio
import logging

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.modules.safety.service.page_table import sync_page_table_mirror
from app.modules.safety.service.special_operation_transcription import (
    SOURCE_PAGE_KEY,
    sync_special_operation_ledger,
)

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.0
RETRY_LOCK_WAIT_SECONDS = 20.0
RETRY_LOCK_MAX = 15

_task: dict[str, asyncio.Task[None]] = {}
_state: dict[str, str] = {}  # page_key -> "syncing"
_rerun: set[str] = set()


def schedule_page_mirror_refresh(page_key: str) -> None:
    """记录变更事件后调用：去抖后立即同步该页镜像。

    防抖等待期收到新事件 → 取消旧任务重新计时（合并）；
    同步进行中收到新事件 → 记 rerun，本轮结束后自动再跑一轮。
    """
    if page_key in _state:
        _rerun.add(page_key)
        return
    task = _task.get(page_key)
    if task is not None and not task.done():
        task.cancel()  # 只会取消防抖等待期，不会打断同步
    _task[page_key] = asyncio.create_task(_refresh(page_key))


async def _refresh(page_key: str) -> None:
    cancelled = False
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        for attempt in range(RETRY_LOCK_MAX + 1):
            _state[page_key] = "syncing"
            try:
                async with async_session_factory() as session:
                    await sync_page_table_mirror(session, page_key)
                    if page_key == SOURCE_PAGE_KEY:
                        await sync_special_operation_ledger(session)
                logger.info("事件驱动镜像同步完成: page=%s", page_key)
                return
            except AppException as exc:
                if (
                    getattr(exc, "status_code", None) == 409
                    and attempt < RETRY_LOCK_MAX
                ):
                    await asyncio.sleep(RETRY_LOCK_WAIT_SECONDS)
                    continue
                raise
            finally:
                _state.pop(page_key, None)
    except asyncio.CancelledError:
        cancelled = True
        raise
    except Exception:
        logger.exception("事件驱动镜像同步失败: page=%s", page_key)
    finally:
        # 只清理自己注册的任务：被新事件取消的旧任务不能弹掉新任务的注册，
        # 否则下一个事件会重复建任务、绕过去抖导致重复同步
        if _task.get(page_key) is asyncio.current_task():
            _task.pop(page_key, None)
        if not cancelled and page_key in _rerun:
            _rerun.discard(page_key)
            schedule_page_mirror_refresh(page_key)
