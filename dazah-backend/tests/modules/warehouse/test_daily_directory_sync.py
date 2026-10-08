"""Daily directory sync must preserve database IDs and persisted sync state."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.warehouse import scheduler
from app.modules.warehouse import service as warehouse_service
from app.modules.warehouse.legacy_models import (
    WarehouseFeishuConfig,
    WarehouseFeishuTable,
)
from app.modules.warehouse.repository import WarehouseRepository
from app.modules.warehouse.service import WarehouseService

DirectorySync = tuple[
    WarehouseService, WarehouseFeishuConfig, WarehouseFeishuTable, Mock
]


@pytest.fixture
def directory_sync(monkeypatch: pytest.MonkeyPatch) -> DirectorySync:
    session = AsyncMock(spec=AsyncSession)
    service = WarehouseService(session)
    config = WarehouseFeishuConfig(
        id=uuid4(), daily_sync_time="00:00", timezone="Asia/Shanghai"
    )
    table = WarehouseFeishuTable(
        id=uuid4(),
        app_token="fixture-base",
        table_id="fixture-table",
        name="Fixture directory table",
        sync_status="discovered",
        field_count=0,
        record_count=0,
        source_path=[],
    )
    assert table.id != service._legacy_table_uuid(table.table_id)
    repo = Mock(spec=WarehouseRepository)
    repo.session = session
    repo.get_active_feishu_config = AsyncMock(return_value=config)
    repo.list_feishu_tables = AsyncMock(return_value=[table])
    repo.get_feishu_table_by_id = AsyncMock(return_value=table)
    repo.list_page_feishu_configs = AsyncMock(return_value=[])
    repo.upsert_page_feishu_config = AsyncMock()
    repo.fail_running_sync_runs = AsyncMock()
    service.repo = repo
    client = Mock()
    client.list_fields = AsyncMock(return_value=[{"field_id": "fixture-field"}])
    client.search_records = AsyncMock(
        return_value={
            "items": [{"record_id": "fixture-record", "fields": {"value": 1}}],
            "total": 1,
            "has_more": False,
        }
    )
    service._build_feishu_client = Mock(return_value=client)
    monkeypatch.setattr(scheduler, "WarehouseService", lambda _session: service)
    return service, config, table, client


@pytest.mark.asyncio
async def test_daily_directory_id_reaches_sync_and_is_not_due_again(
    directory_sync: DirectorySync,
) -> None:
    service, config, table, client = directory_sync
    generator = scheduler.WarehouseFeishuDailySyncGenerator()
    assert await generator.find_due(service.repo.session) == [str(table.id)]

    await generator.execute_one(service.repo.session, str(table.id))

    service.repo.get_feishu_table_by_id.assert_awaited_once_with(table.id, config.id)
    service._build_feishu_client.assert_called_once_with(config, table.app_token)
    client.list_fields.assert_awaited_once_with(table.table_id, page_size=100)
    client.search_records.assert_awaited_once_with(
        table.table_id, page_size=500, page_token=None
    )
    assert table.sync_status == "success"
    assert table.sync_error is None
    assert table.last_synced_at is not None
    assert table.field_count == table.record_count == 1
    assert table.active_mirror_version
    assert service.repo.session.commit.await_count == 2
    assert await generator.find_due(service.repo.session) == []
    service.repo.list_page_feishu_configs.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("provider unavailable"), TimeoutError()]
)
async def test_daily_directory_failure_keeps_watermark_and_persists_failure(
    directory_sync: DirectorySync,
    error: Exception,
) -> None:
    service, _config, table, client = directory_sync
    previous_sync = datetime(2020, 1, 1, tzinfo=UTC)
    table.last_synced_at = previous_sync
    table.active_mirror_version = "previous-version"
    client.list_fields.side_effect = error
    generator = scheduler.WarehouseFeishuDailySyncGenerator()

    with pytest.raises(AppException) as raised:
        await generator.execute_one(service.repo.session, str(table.id))

    assert raised.value.__cause__ is error
    assert raised.value.status_code in (502, 504)
    assert table.sync_status == "failed"
    assert table.sync_error
    assert "provider unavailable" not in table.sync_error
    assert table.last_synced_at == previous_sync
    assert table.active_mirror_version == "previous-version"
    service.repo.session.rollback.assert_awaited_once()
    assert service.repo.session.commit.await_count == 2
    service.repo.fail_running_sync_runs.assert_awaited_once()
    assert service.repo.fail_running_sync_runs.call_args.args == (table.id,)
    assert (
        service.repo.fail_running_sync_runs.call_args.kwargs["error_message"]
        == table.sync_error
    )
    assert await generator.find_due(service.repo.session) == [str(table.id)]


@pytest.mark.asyncio
async def test_daily_directory_revalidates_active_config_before_access(
    directory_sync: DirectorySync,
) -> None:
    service, config, table, client = directory_sync
    service.repo.get_feishu_table_by_id.return_value = None
    generator = scheduler.WarehouseFeishuDailySyncGenerator()

    with pytest.raises(AppException):
        await generator.execute_one(service.repo.session, str(table.id))

    service.repo.get_feishu_table_by_id.assert_awaited_once_with(table.id, config.id)
    client.list_fields.assert_not_awaited()
    client.search_records.assert_not_awaited()
    service.repo.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_directory_without_active_config_never_contacts_feishu(
    directory_sync: DirectorySync,
) -> None:
    service, _config, table, client = directory_sync
    service.repo.get_active_feishu_config.return_value = None
    generator = scheduler.WarehouseFeishuDailySyncGenerator()

    assert await generator.find_due(service.repo.session) == []
    with pytest.raises(AppException):
        await generator.execute_one(service.repo.session, str(table.id))

    service.repo.get_feishu_table_by_id.assert_not_awaited()
    client.list_fields.assert_not_awaited()
    service.repo.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_directory_records_unexpected_error_without_masking_it(
    directory_sync: DirectorySync,
) -> None:
    service, _config, table, client = directory_sync
    error = TypeError("unexpected internal error")
    client.list_fields.side_effect = error

    with pytest.raises(TypeError) as raised:
        await scheduler.WarehouseFeishuDailySyncGenerator().execute_one(
            service.repo.session, str(table.id)
        )

    assert raised.value is error
    assert table.sync_status == "failed"
    assert table.last_synced_at is None
    service.repo.session.rollback.assert_awaited_once()
    assert service.repo.session.commit.await_count == 2


@pytest.mark.asyncio
async def test_daily_directory_deadline_cancels_provider_and_marks_failed(
    directory_sync: DirectorySync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _config, table, client = directory_sync
    cancelled = False

    async def stalled_fields(*_args: object, **_kwargs: object) -> None:
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True

    client.list_fields.side_effect = stalled_fields
    monkeypatch.setattr(
        warehouse_service, "WAREHOUSE_FEISHU_TABLE_SYNC_TIMEOUT_SECONDS", 0.01
    )

    with pytest.raises(AppException) as raised:
        await scheduler.WarehouseFeishuDailySyncGenerator().execute_one(
            service.repo.session, str(table.id)
        )

    assert raised.value.status_code == 504
    assert isinstance(raised.value.__cause__, TimeoutError)
    assert cancelled
    assert table.sync_status == "failed"
    assert table.last_synced_at is None
    service.repo.session.rollback.assert_awaited_once()
    service.repo.fail_running_sync_runs.assert_awaited_once()
