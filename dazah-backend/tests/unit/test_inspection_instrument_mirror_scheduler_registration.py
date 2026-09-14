"""仪器管理镜像定时任务注册守护测试。

main.py lifespan 将两个镜像生成器注册进统一调度引擎；任务重名会在
启动时抛 ValueError 导致应用无法启动，这里守护名称唯一且可注册。
"""

from __future__ import annotations

import pytest

from app.modules.quality.scheduled import (
    InspectionInstrumentMirrorFullSyncGenerator,
    InspectionInstrumentMirrorSyncGenerator,
)
from app.platform.scheduler.registry import SchedulerRegistry


def test_instrument_mirror_generators_register_with_unique_names() -> None:
    sync_gen = InspectionInstrumentMirrorSyncGenerator()
    full_gen = InspectionInstrumentMirrorFullSyncGenerator()

    assert sync_gen.name == "quality.inspection_instrument_mirror_sync"
    assert full_gen.name == "quality.inspection_instrument_mirror_full_sync"

    registry = SchedulerRegistry()
    registry.register_generator(sync_gen)
    registry.register_generator(full_gen)

    with pytest.raises(ValueError):
        registry.register_generator(InspectionInstrumentMirrorSyncGenerator())
