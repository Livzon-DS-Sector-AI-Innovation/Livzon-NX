"""生产计划飞书表定时同步生成器测试（节拍/过滤/执行分发）。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.modules.production import scheduled as plan_scheduled
from app.modules.production.scheduled import ProductionPlanFeishuSyncGenerator


def test_schedule_is_ten_minute_interval_all_day() -> None:
    """对齐仓储同步机制：10 分钟 INTERVAL 高频节拍，全天无夜间空窗。"""
    gen = ProductionPlanFeishuSyncGenerator()
    assert gen.schedule.timezone == "Asia/Shanghai"
    assert gen.schedule.strategy.value == "interval"
    assert gen.schedule.interval_seconds == 600


async def test_find_due_returns_only_active_plan_configs() -> None:
    """只同步启用中、未删除、target=production_plan/sales_plan/fl_batch 的配置。"""
    session = MagicMock()
    ids = [uuid.uuid4(), uuid.uuid4()]
    result = MagicMock()
    result.scalars.return_value.all.return_value = ids
    session.execute = AsyncMock(return_value=result)

    due = await ProductionPlanFeishuSyncGenerator().find_due(session)

    assert due == [str(i) for i in ids]
    # 确认查询带了过滤条件（active / 未删除 / sync_target 含计划与 FL 批次）
    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile()
    assert "is_active" in str(compiled)
    assert "is_deleted" in str(compiled)
    assert "sync_target IN" in str(compiled)
    # expanding IN 的参数值为列表，展开后校验三类目标都在过滤范围内
    param_values: set[Any] = set()
    for value in compiled.params.values():
        if isinstance(value, (list, tuple)):
            param_values.update(value)
        else:
            param_values.add(value)
    assert {"production_plan", "sales_plan", "fl_batch"} <= param_values


async def test_execute_one_dispatches_sync_by_target(monkeypatch: Any) -> None:
    """执行时按配置分发到同步逻辑。"""
    config = SimpleNamespace(id=uuid.uuid4())
    session = MagicMock()
    session.get = AsyncMock(return_value=config)

    called: dict[str, Any] = {}

    async def fake_sync(cfg: Any, sess: Any) -> dict[str, Any]:
        called["config_id"] = cfg.id
        return {}

    monkeypatch.setattr(plan_scheduled, "sync_config_by_target", fake_sync)

    await ProductionPlanFeishuSyncGenerator().execute_one(session, str(config.id))

    assert called["config_id"] == config.id


async def test_execute_one_skips_missing_config(monkeypatch: Any) -> None:
    """配置已被删除时静默跳过，不触发同步。"""
    session = MagicMock()
    session.get = AsyncMock(return_value=None)

    async def fail_sync(cfg: Any, sess: Any) -> dict[str, Any]:
        raise AssertionError("配置不存在时不应触发同步")

    monkeypatch.setattr(plan_scheduled, "sync_config_by_target", fail_sync)

    await ProductionPlanFeishuSyncGenerator().execute_one(session, str(uuid.uuid4()))
