"""安全模块镜像同步与隐患到期提醒调度注册守护测试。

main.py lifespan 启动独立镜像同步循环（mirror_sync_loop）并把
SafetyHazardDueReminderGenerator 注册进统一调度引擎；任务重名会在
启动时抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册，
并守护循环的协作退出语义（stop 置位后循环可被取消收尾）。
"""

from __future__ import annotations

import asyncio

import pytest

from app.modules.safety.scheduled import (
    MIRROR_SYNC_INTERVAL,
    SafetyHazardDueReminderGenerator,
    mirror_sync_loop,
)
from app.platform.scheduler.registry import SchedulerRegistry


def test_hazard_due_reminder_generator_registers_with_unique_name() -> None:
    gen = SafetyHazardDueReminderGenerator()

    assert gen.name == "safety.hazard_due_daily"

    registry = SchedulerRegistry()
    registry.register_generator(gen)
    with pytest.raises(ValueError):
        registry.register_generator(SafetyHazardDueReminderGenerator())


def test_mirror_sync_loop_runs_until_stop_then_finishes(monkeypatch) -> None:
    """循环在 stop 置位后自然退出，不留悬挂任务。"""

    async def _run() -> None:
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from app.modules.safety import scheduled as scheduled_module
        from app.modules.safety.service import page_table

        # 循环第一轮就会开真实会话连库；单测注入假会话，专注退出语义
        @asynccontextmanager
        async def _fake_factory():
            yield SimpleNamespace(commit=AsyncMock(return_value=None))

        monkeypatch.setattr(page_table, "async_session_factory", _fake_factory)

        # 循环每轮 sleep(interval) 后检查 stop；用短间隔让 stop 能及时生效
        original_interval = scheduled_module.MIRROR_SYNC_INTERVAL
        original_stop = scheduled_module._mirror_sync_stop
        scheduled_module.MIRROR_SYNC_INTERVAL = original_interval.__class__(
            milliseconds=50
        )
        stop = asyncio.Event()
        scheduled_module._mirror_sync_stop = stop
        try:
            task = asyncio.create_task(mirror_sync_loop())
            await asyncio.sleep(0.05)
            assert not task.done()
            stop.set()
            await asyncio.wait_for(task, timeout=2)
        finally:
            scheduled_module.MIRROR_SYNC_INTERVAL = original_interval
            scheduled_module._mirror_sync_stop = original_stop

    asyncio.run(_run())


def test_mirror_sync_interval_is_fifteen_minutes() -> None:
    # main.py 以该间隔启动独立循环；改动需同步调整 lifespan 侧注释
    assert MIRROR_SYNC_INTERVAL.total_seconds() == 15 * 60
