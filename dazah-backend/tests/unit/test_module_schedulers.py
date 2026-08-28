"""Unit tests for module-specific TaskGenerator implementations."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.modules.energy import scheduler as energy_scheduler
from app.modules.equipment import scheduler as equipment_scheduler
from app.modules.production.repository import ProductionRepository
from app.modules.warehouse import scheduler as warehouse_scheduler
from app.platform.identity import scheduler as identity_scheduler
from app.platform.integrations.feishu import read_scheduler

SimpleNamespace: Any = _SimpleNamespace


@pytest.mark.asyncio
async def test_energy_scheduler_handles_inactive_and_active_configs(
    monkeypatch: Any,
) -> None:
    config_id = uuid4()
    repo: Any = SimpleNamespace(get_config=AsyncMock(return_value=None))
    service: Any = SimpleNamespace(
        repo=repo,
        run_scheduled_sync_if_due=AsyncMock(),
    )
    monkeypatch.setattr(energy_scheduler, "EnergyWikiService", lambda _session: service)
    generator = energy_scheduler.EnergyWikiSyncGenerator()

    assert await generator.find_due(object()) == []
    repo.get_config.return_value = SimpleNamespace(id=config_id, is_active=False)
    assert await generator.find_due(object()) == []
    repo.get_config.return_value = SimpleNamespace(id=config_id, is_active=True)
    assert await generator.find_due(object()) == [str(config_id)]
    await generator.execute_one(object(), str(config_id))
    service.run_scheduled_sync_if_due.assert_awaited_once()


@pytest.mark.asyncio
async def test_warehouse_daily_scheduler_selects_due_tables(monkeypatch: Any) -> None:
    config_id = uuid4()
    due_id = uuid4()
    current_id = uuid4()
    config: Any = SimpleNamespace(
        id=config_id,
        daily_sync_time="00:00",
        timezone="Asia/Shanghai",
    )
    repo: Any = SimpleNamespace(
        get_active_feishu_config=AsyncMock(return_value=config),
        list_feishu_tables=AsyncMock(
            return_value=[
                SimpleNamespace(id=due_id, last_synced_at=None),
                SimpleNamespace(id=current_id, last_synced_at=datetime.now(UTC)),
            ]
        ),
        claim_queued_analysis_runs=AsyncMock(return_value=[SimpleNamespace(id=due_id)]),
    )
    service: Any = SimpleNamespace(
        repo=repo,
        sync_feishu_table=AsyncMock(),
        execute_analysis_run=AsyncMock(),
    )
    monkeypatch.setattr(
        warehouse_scheduler,
        "WarehouseService",
        lambda _session: service,
    )

    daily = warehouse_scheduler.WarehouseFeishuDailySyncGenerator()
    assert await daily.find_due(object()) == [str(due_id)]
    await daily.execute_one(object(), str(due_id))
    service.sync_feishu_table.assert_awaited_once()

    analysis = warehouse_scheduler.WarehouseFeishuAnalysisGenerator()
    assert await analysis.find_due(object()) == [str(due_id)]
    await analysis.execute_one(object(), str(due_id))
    service.execute_analysis_run.assert_awaited_once()

    repo.get_active_feishu_config.return_value = None
    assert await daily.find_due(object()) == []
    repo.get_active_feishu_config.return_value = SimpleNamespace(
        id=config_id,
        daily_sync_time="invalid",
        timezone="invalid",
    )
    assert await daily.find_due(object()) == []


@pytest.mark.asyncio
async def test_daily_read_mirror_finds_only_stale_resources(monkeypatch: Any) -> None:
    stale_id = uuid4()
    current_id = uuid4()
    resources = [
        SimpleNamespace(id=stale_id, last_complete_sync_at=None),
        SimpleNamespace(id=current_id, last_complete_sync_at=datetime.now(UTC)),
        SimpleNamespace(
            id=uuid4(),
            last_complete_sync_at=datetime.now(UTC) - timedelta(days=1),
        ),
    ]
    result: Any = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: resources)
    )
    session: Any = SimpleNamespace(execute=AsyncMock(return_value=result))
    generator = read_scheduler.ProductionFeishuReadDailySyncGenerator()

    class MorningDateTime:
        @classmethod
        def now(cls: Any, tz: Any = None) -> Any:
            value = datetime(2026, 1, 2, 3, tzinfo=tz or UTC)
            return value

    monkeypatch.setattr(read_scheduler, "datetime", MorningDateTime)
    due = await generator.find_due(session)
    assert str(stale_id) in due
    assert str(current_id) not in due

    class EarlyDateTime:
        @classmethod
        def now(cls: Any, tz: Any = None) -> Any:
            return datetime(2026, 1, 2, 1, tzinfo=tz or UTC)

    monkeypatch.setattr(read_scheduler, "datetime", EarlyDateTime)
    assert await generator.find_due(session) == []


@pytest.mark.asyncio
async def test_read_mirror_execute_skips_missing_credentials(monkeypatch: Any) -> None:
    production_session: Any = object()
    production_repo: Any = SimpleNamespace(
        get_active_feishu_config=AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        read_scheduler,
        "ProductionRepository",
        lambda _session: production_repo,
    )
    await read_scheduler.ProductionFeishuReadDailySyncGenerator().execute_one(
        production_session,
        uuid4(),
    )

    config = SimpleNamespace(
        app_id="production-app",
        encrypted_app_secret="encrypted-secret",
    )
    production_repo.get_active_feishu_config.return_value = config
    mirror = SimpleNamespace(sync_resource=AsyncMock())
    monkeypatch.setattr(
        read_scheduler,
        "ModuleFeishuReadMirrorService",
        lambda *_args, **_kwargs: mirror,
    )
    monkeypatch.setattr(read_scheduler, "decrypt_secret", lambda _value: "secret")
    resource_id = uuid4()
    await read_scheduler.ProductionFeishuReadDailySyncGenerator().execute_one(
        production_session,
        resource_id,
    )
    mirror.sync_resource.assert_awaited_once_with(UUID(str(resource_id)))

    quality_session: Any = SimpleNamespace(scalar=AsyncMock(return_value=None))
    await read_scheduler.QualityFeishuReadDailySyncGenerator().execute_one(
        quality_session,
        uuid4(),
    )


@pytest.mark.asyncio
async def test_production_repository_reads_active_feishu_config() -> None:
    config = SimpleNamespace(id=uuid4())
    result = SimpleNamespace(scalar_one_or_none=lambda: config)
    session: Any = SimpleNamespace(execute=AsyncMock(return_value=result))

    found = await ProductionRepository(session).get_active_feishu_config()

    assert found is config
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_identity_member_sync_skips_missing_target(monkeypatch: Any) -> None:
    identity_scheduler.stop_member_sync_flag.clear()
    monkeypatch.setattr(
        identity_scheduler,
        "get_settings",
        lambda: SimpleNamespace(FEISHU_SYNC_MEMBER_DEPT_ID=""),
    )
    await identity_scheduler.member_sync_loop()


@pytest.mark.asyncio
async def test_identity_member_sync_contains_sync_failure(monkeypatch: Any) -> None:
    identity_scheduler.stop_member_sync_flag.clear()
    monkeypatch.setattr(
        identity_scheduler,
        "get_settings",
        lambda: SimpleNamespace(FEISHU_SYNC_MEMBER_DEPT_ID="department"),
    )
    sync_members: Any = AsyncMock(side_effect=RuntimeError("Feishu unavailable"))
    monkeypatch.setattr(
        "app.platform.integrations.feishu.sync.sync_members",
        sync_members,
    )
    wait_count = 0

    async def fake_wait_for(awaitable: Any, *, timeout: Any) -> Any:
        nonlocal wait_count
        awaitable.close()
        wait_count += 1
        if wait_count == 1:
            raise TimeoutError
        identity_scheduler.stop_member_sync_flag.set()

    monkeypatch.setattr(identity_scheduler.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    await identity_scheduler.member_sync_loop()
    sync_members.assert_awaited_once_with("department")
    identity_scheduler.stop_member_sync_flag.clear()


@pytest.mark.asyncio
async def test_equipment_maintenance_loop_handles_disabled_setting(
    monkeypatch: Any,
) -> None:
    equipment_scheduler.stop_maintenance_plan_flag.clear()
    monkeypatch.setattr(
        equipment_scheduler,
        "get_settings",
        lambda: SimpleNamespace(MAINTENANCE_PLAN_AUTO_ENABLED=False),
    )
    await equipment_scheduler.maintenance_plan_loop()


@pytest.mark.asyncio
async def test_equipment_maintenance_loop_commits_and_stops(monkeypatch: Any) -> None:
    equipment_scheduler.stop_maintenance_plan_flag.clear()
    monkeypatch.setattr(
        equipment_scheduler,
        "get_settings",
        lambda: SimpleNamespace(MAINTENANCE_PLAN_AUTO_ENABLED=True),
    )

    class FixedDateTime:
        @classmethod
        def now(cls: Any, tz: Any = None) -> Any:
            return datetime(2026, 1, 1, 0, 1, tzinfo=tz or UTC)

    monkeypatch.setattr(equipment_scheduler, "datetime", FixedDateTime)
    wait_count = 0

    async def fake_wait_for(awaitable: Any, *, timeout: Any) -> Any:
        nonlocal wait_count
        awaitable.close()
        wait_count += 1
        if wait_count == 1:
            raise TimeoutError
        equipment_scheduler.stop_maintenance_plan_flag.set()

    monkeypatch.setattr(equipment_scheduler.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    session: Any = SimpleNamespace(commit=AsyncMock())

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return session

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(
        equipment_scheduler,
        "async_session_factory",
        SessionContext,
    )
    generate: Any = AsyncMock(return_value=(2, 1))
    monkeypatch.setattr(
        "app.modules.equipment.service.maintenance_plan.generate_due_work_orders",
        generate,
    )

    await equipment_scheduler.maintenance_plan_loop()
    generate.assert_awaited_once_with(session)
    session.commit.assert_awaited_once()
    equipment_scheduler.stop_maintenance_plan_flag.clear()


@pytest.mark.asyncio
async def test_equipment_timeout_scan_notifies_only_expired_orders(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(FEISHU_EQUIPMENT_DEPT_ID="department"),
    )
    expired: Any = SimpleNamespace(
        priority="紧急",
        reported_at=datetime.now(UTC) - timedelta(minutes=20),
        work_order_no="WO-1",
    )
    current: Any = SimpleNamespace(
        priority="低",
        reported_at=datetime.now(UTC),
        work_order_no="WO-2",
    )
    result: Any = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [expired, current])
    )
    session: Any = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        rollback=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self: Any) -> Any:
            return session

        async def __aexit__(self: Any, *_args: Any) -> Any:
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        SessionContext,
    )
    monkeypatch.setattr(
        "app.modules.equipment.service.maintenance_config.get_claim_timeout_config",
        AsyncMock(
            return_value=SimpleNamespace(
                emergency=5,
                high=10,
                medium=15,
                low=60,
            )
        ),
    )
    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_department_leader",
        AsyncMock(return_value=None),
    )
    notify: Any = AsyncMock()
    monkeypatch.setattr(
        "app.platform.integrations.feishu.message.send_timeout_notification",
        notify,
    )

    await equipment_scheduler.scan_timeout_work_orders()
    notify.assert_awaited_once_with("WO-1", "设备", "主管")
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_equipment_timeout_scan_skips_without_department(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(FEISHU_EQUIPMENT_DEPT_ID=""),
    )
    await equipment_scheduler.scan_timeout_work_orders()


@pytest.mark.asyncio
async def test_equipment_timeout_loop_contains_scan_failure(monkeypatch: Any) -> None:
    equipment_scheduler.stop_timeout_flag.clear()
    monkeypatch.setattr(
        equipment_scheduler,
        "scan_timeout_work_orders",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    async def fake_wait_for(awaitable: Any, *, timeout: Any) -> Any:
        awaitable.close()
        equipment_scheduler.stop_timeout_flag.set()
        raise TimeoutError

    monkeypatch.setattr(equipment_scheduler.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    await equipment_scheduler.timeout_scan_loop()
    equipment_scheduler.stop_timeout_flag.clear()
