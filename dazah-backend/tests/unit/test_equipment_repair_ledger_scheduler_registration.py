"""设备检修镜像定时任务注册守护测试。

main.py lifespan 将检修镜像生成器注册进统一调度引擎；任务重名会在
启动时抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册，
并确认启动入口确实完成了注册。
"""

from __future__ import annotations

import inspect

import pytest

from app.main import lifespan as app_lifespan
from app.modules.equipment.scheduled import RepairLedgerMirrorSyncGenerator
from app.platform.scheduler.registry import SchedulerRegistry


def test_repair_ledger_generator_registers_with_unique_name() -> None:
    generator = RepairLedgerMirrorSyncGenerator()

    assert generator.name == "equipment.repair_ledger_mirror_sync"
    # 每 30 分钟增量同步一次
    assert generator.schedule.interval_seconds == 1800

    registry = SchedulerRegistry()
    registry.register_generator(generator)

    with pytest.raises(ValueError):
        registry.register_generator(RepairLedgerMirrorSyncGenerator())


def test_lifespan_registers_repair_ledger_generator() -> None:
    source = inspect.getsource(app_lifespan)

    assert "register_generator(RepairLedgerMirrorSyncGenerator())" in source
