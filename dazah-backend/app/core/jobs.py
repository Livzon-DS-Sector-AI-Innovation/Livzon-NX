"""后台任务提交模块。

用于异步提交长时间运行的任务，通过 Redis 存储任务状态。
符合《后端AI编程规范》：HTTP 请求禁止超过 5 秒，一次性异步任务使用 jobs.py。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from app.core.redis import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

# 心跳间隔与心跳键存活时间：进程重启后心跳停止，心跳键在 HEARTBEAT_TTL 内过期，
# 孤儿 running 状态最多在 HEARTBEAT_TTL 后被识别为"非运行"。
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = 30


def _heartbeat_key(job_id: str) -> str:
    return f"{job_id}:hb"


async def submit_job(
    fn: Callable[..., Awaitable[Any]],
    task_id: str | None = None,
    *,
    ttl: int = 600,
    status_extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    """提交一个异步后台任务，立即返回任务 ID。

    任务状态通过 Redis 存储，可通过 get_job_status() 查询。
    运行期间通过独立心跳键证明任务存活；进程重启导致任务中断后，
    心跳键过期，is_job_running() 会将残留的 running 状态视为孤儿。

    Args:
        fn: 异步任务函数
        task_id: 任务 ID，不传则自动生成
        ttl: 任务状态在 Redis 中的存活时间（秒）
        status_extra: 附加初始状态字段（如 owner），随状态一起存储；
            查询方可用于归属校验。默认 None 不附加任何字段。
        **kwargs: 传给 fn 的参数

    Returns:
        任务 ID
    """
    job_id = task_id or f"job:{uuid4().hex[:12]}"

    # 初始化任务状态 + 心跳键
    initial_status = {"state": "running", "progress": "启动中...", "result": None}
    if status_extra:
        initial_status.update(status_extra)
    await cache_set(job_id, json.dumps(initial_status, ensure_ascii=False), ex=ttl)
    await cache_set(_heartbeat_key(job_id), "1", ex=HEARTBEAT_TTL_SECONDS)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                await cache_set(_heartbeat_key(job_id), "1", ex=HEARTBEAT_TTL_SECONDS)
            except Exception:
                logger.exception("Job %s heartbeat failed", job_id)

    async def _run() -> None:
        hb = asyncio.create_task(_heartbeat())
        try:
            result = await fn(**kwargs)
            status = {"state": "completed", "progress": "完成", "result": result}
        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            status = {"state": "failed", "progress": f"失败: {str(e)}", "result": None}
        finally:
            hb.cancel()
            await cache_delete(_heartbeat_key(job_id))
        await cache_set(
            job_id, json.dumps(status, ensure_ascii=False), ex=min(ttl, 300)
        )

    # 使用 asyncio.create_task 启动后台执行
    # 规范禁止 create_task 处理业务逻辑，但 jobs.py 是规范指定的
    # 一次性异步任务机制，属于基础设施层
    asyncio.create_task(_run())

    return job_id


async def is_job_running(job_id: str) -> bool:
    """判断后台任务是否真正在运行。

    running 状态但心跳键已过期（进程重启中断）视为孤儿状态，返回 False，
    调用方可安全地重新提交任务。
    """
    status = await get_job_status(job_id)
    if not status or status.get("state") != "running":
        return False
    return await cache_get(_heartbeat_key(job_id)) is not None


async def get_job_status(job_id: str) -> dict[str, Any] | None:
    """查询任务状态。

    Args:
        job_id: 任务 ID

    Returns:
        任务状态字典，不存在返回 None
    """
    raw = await cache_get(job_id)
    if not raw:
        return None
    return cast(dict[str, Any], json.loads(raw))


async def update_job_progress(job_id: str, progress: str, *, ttl: int = 600) -> None:
    """更新后台任务的进度文案（任务仍处于 running 状态时）。

    用于长时间任务向调用方报告中间进度（如"正在生成第 3/15 份文件…"）。
    在不改变其余状态字段的前提下仅更新 progress 字段，保持任务心跳键不变。

    Args:
        job_id: 任务 ID（submit_job 返回值）
        progress: 新的进度文案
        ttl: 更新后的状态在 Redis 中的存活时间（秒），默认与 submit_job 一致
    """
    raw = await cache_get(job_id)
    if not raw:
        return  # 任务状态不存在（已被清理或从未提交），静默忽略
    status = json.loads(raw)
    if status.get("state") != "running":
        return  # 已结束的任务不再更新进度
    status["progress"] = progress
    await cache_set(job_id, json.dumps(status, ensure_ascii=False), ex=ttl)
