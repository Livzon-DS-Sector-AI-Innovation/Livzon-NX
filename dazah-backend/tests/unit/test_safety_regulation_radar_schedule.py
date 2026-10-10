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


class _FakeSession:
    """只回放 find_due 需要的查询结果，避免触碰真实设置表。"""

    def __init__(self, row: Any) -> None:
        self._row = row

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        row = self._row

        class _Result:
            def scalar_one_or_none(self) -> Any:
                return row

        return _Result()


@pytest.mark.anyio
async def test_find_due_respects_scan_switch() -> None:
    """自动扫描开关关闭或尚未保存配置时跳过；开启时每周期返回一个待办项。"""
    from types import SimpleNamespace

    generator = scheduled.SafetyRegulationRadarGenerator()

    # 尚无配置行：跳过（没有任何可写入的目标）
    assert await generator.find_due(_FakeSession(None)) == []
    # 设置了但开关关闭：跳过
    assert (
        await generator.find_due(
            _FakeSession(SimpleNamespace(radar_scan_enabled=False))
        )
        == []
    )
    # 开关开启：返回单个待办项
    assert await generator.find_due(
        _FakeSession(SimpleNamespace(radar_scan_enabled=True))
    ) == [True]


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
