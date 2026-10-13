"""五金备件同步定时任务注册守护测试。

main.py lifespan 将备件同步生成器注册进统一调度引擎；任务重名会在
启动时抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册。
"""

from __future__ import annotations

import pytest

from app.modules.equipment.scheduled import SparePartHardwareSyncGenerator
from app.platform.scheduler.registry import SchedulerRegistry


def test_spare_part_hardware_generator_registers_with_unique_name() -> None:
    generator = SparePartHardwareSyncGenerator()

    assert generator.name == "equipment.spare_part_hardware_sync"
    assert generator.schedule.interval_seconds == 3600

    registry = SchedulerRegistry()
    registry.register_generator(generator)

    with pytest.raises(ValueError):
        registry.register_generator(SparePartHardwareSyncGenerator())
