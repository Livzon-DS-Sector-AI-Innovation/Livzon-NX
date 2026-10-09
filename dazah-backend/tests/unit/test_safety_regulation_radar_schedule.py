"""法规雷达定时任务（main.py 注册的 SafetyRegulationRadarGenerator）契约测试。"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.safety import scheduled
from app.platform.scheduler import ScheduleStrategy


def test_generator_contract_is_weekly_cron_in_shanghai() -> None:
    generator = scheduled.SafetyRegulationRadarGenerator()

    assert generator.name == "safety.regulation_radar_weekly"
    assert generator.schedule.strategy is ScheduleStrategy.CRON
    assert generator.schedule.expression == "0 8 * * 1"
    assert generator.schedule.timezone == "Asia/Shanghai"
    # 抓取 5 个站点 + AI 过滤 + 写飞书，超时放宽到 30 分钟
    assert generator.timeout_seconds == 1800


@pytest.mark.anyio
async def test_find_due_is_unconditional(monkeypatch: Any) -> None:
    """雷达是数据发现底座，不受通知开关影响，每周期固定返回一个待办项。"""
    generator = scheduled.SafetyRegulationRadarGenerator()

    assert await generator.find_due(object()) == [True]


@pytest.mark.anyio
async def test_execute_one_runs_radar_without_dry_run(monkeypatch: Any) -> None:
    run_radar = AsyncMock(
        return_value={
            "status": "success",
            "new_count": 2,
            "revised_count": 1,
            "skipped_count": 3,
            "errors": [],
        }
    )
    monkeypatch.setattr(scheduled.regulation_radar, "run_radar", run_radar)
    generator = scheduled.SafetyRegulationRadarGenerator()
    session = object()

    await generator.execute_one(session, True)

    run_radar.assert_awaited_once_with(session, dry_run=False, trigger="schedule")
