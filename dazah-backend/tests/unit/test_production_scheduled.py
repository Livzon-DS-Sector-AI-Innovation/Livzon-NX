"""生产计划飞书表定时同步生成器测试（窗口/过滤/执行分发）。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.modules.production import scheduled as plan_scheduled
from app.modules.production.scheduled import ProductionPlanHourlySyncGenerator


def test_cron_covers_only_8_to_20_beijing() -> None:
    """cron 表达式限北京时间 8-20 点整点，其余时段不触发。"""
    gen = ProductionPlanHourlySyncGenerator()
    assert gen.schedule.timezone == "Asia/Shanghai"
    assert gen.schedule.strategy.value == "cron"
    hours = gen.schedule.expression.split()[1]
    assert hours == "8-20"
    assert gen.schedule.expression.split()[0] == "0"


async def test_find_due_returns_only_active_production_plan_configs() -> None:
    """只同步启用中、未删除、target=production_plan 的配置。"""
    session = MagicMock()
    ids = [uuid.uuid4(), uuid.uuid4()]
    result = MagicMock()
    result.scalars.return_value.all.return_value = ids
    session.execute = AsyncMock(return_value=result)

    due = await ProductionPlanHourlySyncGenerator().find_due(session)

    assert due == [str(i) for i in ids]
    # 确认查询带了过滤条件（active / 未删除 / sync_target）
    stmt = session.execute.call_args.args[0]
    compiled = str(stmt.compile())
    assert "is_active" in compiled
    assert "is_deleted" in compiled
    assert "sync_target" in compiled


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

    await ProductionPlanHourlySyncGenerator().execute_one(session, str(config.id))

    assert called["config_id"] == config.id


async def test_execute_one_skips_missing_config(monkeypatch: Any) -> None:
    """配置已被删除时静默跳过，不触发同步。"""
    session = MagicMock()
    session.get = AsyncMock(return_value=None)

    async def fail_sync(cfg: Any, sess: Any) -> dict[str, Any]:
        raise AssertionError("配置不存在时不应触发同步")

    monkeypatch.setattr(plan_scheduled, "sync_config_by_target", fail_sync)

    await ProductionPlanHourlySyncGenerator().execute_one(session, str(uuid.uuid4()))
