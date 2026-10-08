"""Verify directory sync commits and rollback reloads in the dedicated test DB."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.warehouse.legacy_models import (
    WarehouseFeishuConfig,
    WarehouseFeishuSourceRoot,
    WarehouseFeishuTable,
)
from app.modules.warehouse.scheduler import WarehouseFeishuDailySyncGenerator
from app.modules.warehouse.service import WarehouseService


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "provider_failure", "timeout"])
async def test_daily_directory_sync_persists_result_without_expired_orm_access(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    config_id, root_id, table_id = uuid4(), uuid4(), uuid4()
    previous_sync = datetime(2020, 1, 1, tzinfo=UTC)
    config = WarehouseFeishuConfig(
        id=config_id,
        app_id="directory-sync-fixture",
        encrypted_app_secret="",
        daily_sync_time="00:00",
        timezone="UTC",
        is_active=True,
    )
    root = WarehouseFeishuSourceRoot(
        id=root_id,
        config_id=config_id,
        name="Directory sync fixture",
        source_type="base",
        source_url="https://example.test/fixture",
        root_token=str(root_id),
        is_active=True,
    )
    table = WarehouseFeishuTable(
        id=table_id,
        source_root_id=root_id,
        business_domain="warehouse",
        app_token="fixture-base",
        table_id=str(table_id),
        name="Fixture table",
        last_synced_at=previous_sync,
        sync_status="discovered",
        active_mirror_version="previous-version",
    )
    client = Mock()
    client.list_fields = AsyncMock(return_value=[{"field_id": "fixture-field"}])
    client.search_records = AsyncMock(
        return_value={
            "items": [{"record_id": "fixture-record"}],
            "total": 1,
            "has_more": False,
        }
    )
    if outcome != "success":
        client.list_fields.side_effect = (
            TimeoutError() if outcome == "timeout" else RuntimeError("unavailable")
        )
    monkeypatch.setattr(
        WarehouseService, "_build_feishu_client", Mock(return_value=client)
    )
    db_session.add_all([config, root, table])
    await db_session.commit()
    try:
        generator = WarehouseFeishuDailySyncGenerator()
        assert await generator.find_due(db_session) == [str(table_id)]
        if outcome == "success":
            await generator.execute_one(db_session, str(table_id))
        else:
            with pytest.raises(AppException) as raised:
                await generator.execute_one(db_session, str(table_id))
            assert raised.value.status_code == (504 if outcome == "timeout" else 502)

        # Force a fresh read so transient in-memory mutations cannot satisfy this.
        db_session.expire_all()
        persisted = (
            await db_session.execute(
                select(WarehouseFeishuTable).where(WarehouseFeishuTable.id == table_id)
            )
        ).scalar_one()
        if outcome == "success":
            assert persisted.sync_status == "success"
            assert persisted.sync_error is None
            assert persisted.last_synced_at > previous_sync
            assert persisted.field_count == persisted.record_count == 1
            assert persisted.active_mirror_version != "previous-version"
            assert await generator.find_due(db_session) == []
        else:
            assert persisted.sync_status == "failed"
            assert persisted.sync_error
            assert persisted.last_synced_at == previous_sync
            assert persisted.active_mirror_version == "previous-version"
            assert await generator.find_due(db_session) == [str(table_id)]
    finally:
        await db_session.rollback()
        for model, row_id in (
            (WarehouseFeishuTable, table_id),
            (WarehouseFeishuSourceRoot, root_id),
            (WarehouseFeishuConfig, config_id),
        ):
            await db_session.execute(delete(model).where(model.id == row_id))
        await db_session.commit()
