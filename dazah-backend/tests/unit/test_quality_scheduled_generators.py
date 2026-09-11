"""质量模块定时任务生成器：find_due/execute_one 的调度行为单测。

镜像/升级/月度分析生成器共用「实体开关 + 回拉开关」的门控查询；
这里用假 session 验证各生成器把正确的服务函数接到调度引擎上。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.quality import scheduled


def _session_with_settings(rows: list[Any]) -> Any:
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    return SimpleNamespace(execute=AsyncMock(return_value=result))


def _setting(entity_code: str, enabled: bool = True) -> Any:
    return SimpleNamespace(
        entity_code=entity_code,
        is_enabled=enabled,
        enable_pull_from_feishu=enabled,
    )


@pytest.mark.anyio
async def test_items_mirror_generators_gate_by_pull_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_gen = scheduled.InspectionItemsMirrorSyncGenerator()
    full_gen = scheduled.InspectionItemsMirrorFullSyncGenerator()
    session = _session_with_settings(
        [
            _setting("qc_items_inventory", True),
            _setting("qc_items_inbound", False),
            _setting("qc_items_outbound", True),
        ]
    )
    assert await sync_gen.find_due(session) == [
        "qc_items_inventory",
        "qc_items_outbound",
    ]
    assert await full_gen.find_due(session) == [
        "qc_items_inventory",
        "qc_items_outbound",
    ]

    exec_mock = AsyncMock()
    monkeypatch.setattr(scheduled, "sync_items_page", exec_mock)
    await sync_gen.execute_one(session, "qc_items_inventory")
    exec_mock.assert_awaited_once_with(session, "qc_items_inventory", incremental=True)
    await full_gen.execute_one(session, "qc_items_outbound")
    assert exec_mock.await_count == 2
    assert exec_mock.await_args_list[1].kwargs["incremental"] is False


@pytest.mark.anyio
async def test_material_mirror_generators_route_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_gen = scheduled.InspectionMaterialMirrorSyncGenerator()
    full_gen = scheduled.InspectionMaterialMirrorFullSyncGenerator()
    session = _session_with_settings(
        [_setting("qc_solid_ys001"), _setting("qc_solid_ys002", False)]
    )
    assert await sync_gen.find_due(session) == ["qc_solid_ys001"]

    exec_mock = AsyncMock()
    monkeypatch.setattr(scheduled, "sync_material_page", exec_mock)
    await sync_gen.execute_one(session, "qc_solid_ys001")
    exec_mock.assert_awaited_once_with(
        session, "qc_solid_ys001", incremental=True
    )
    await full_gen.execute_one(session, "qc_solid_ys001")
    assert exec_mock.await_args_list[1].kwargs["incremental"] is False


@pytest.mark.anyio
async def test_finished_mirror_generators_route_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_gen = scheduled.InspectionFinishedMirrorSyncGenerator()
    full_gen = scheduled.InspectionFinishedMirrorFullSyncGenerator()
    session = _session_with_settings([_setting("qc_finished_fcc14")])
    assert await sync_gen.find_due(session) == ["qc_finished_fcc14"]

    exec_mock = AsyncMock()
    monkeypatch.setattr(scheduled, "sync_finished_page", exec_mock)
    await sync_gen.execute_one(session, "qc_finished_fcc14")
    exec_mock.assert_awaited_once_with(
        session, "qc_finished_fcc14", incremental=True
    )
    await full_gen.execute_one(session, "qc_finished_fcc14")
    assert exec_mock.await_args_list[1].kwargs["incremental"] is False


@pytest.mark.anyio
async def test_escalation_generator_delegates_to_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen = scheduled.TrendAlertEscalationGenerator()
    item = SimpleNamespace(id="row-1")
    find_mock = AsyncMock(return_value=[item])
    monkeypatch.setattr(scheduled, "find_due_trend_alert_escalations", find_mock)
    process_mock = AsyncMock()
    monkeypatch.setattr(
        scheduled, "process_trend_alert_escalation", process_mock
    )

    session = SimpleNamespace()
    assert await gen.find_due(session) == [item]
    await gen.execute_one(session, item)
    process_mock.assert_awaited_once_with(session, item)


@pytest.mark.anyio
async def test_monthly_analysis_generator_delegates_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen = scheduled.TrendAlertMonthlyAnalysisGenerator()
    find_mock = AsyncMock(return_value=["2026-09"])
    monkeypatch.setattr(scheduled, "find_due_trend_monthly_analysis", find_mock)
    run_mock = AsyncMock(return_value={"status": "done"})
    monkeypatch.setattr(scheduled, "run_trend_monthly_analysis", run_mock)

    session = SimpleNamespace()
    assert await gen.find_due(session) == ["2026-09"]
    await gen.execute_one(session, "2026-09")
    run_mock.assert_awaited_once_with(session, "2026-09")
