from unittest.mock import AsyncMock

import pytest

from app.modules.production import fa_acid_sync, fa_feishu_scheduler


@pytest.mark.asyncio
async def test_acid_sync_does_not_clear_data_without_module_config(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        fa_feishu_scheduler,
        "_get_fa_spreadsheet_config",
        AsyncMock(side_effect=RuntimeError("missing module config")),
    )
    read = AsyncMock()
    monkeypatch.setattr(fa_acid_sync, "_read", read)
    with pytest.raises(RuntimeError, match="missing module"):
        await fa_acid_sync.run(db)
    read.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_acid_sync_passes_production_credentials_before_reading(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        fa_feishu_scheduler,
        "_get_fa_spreadsheet_config",
        AsyncMock(
            return_value={"app_id": "production-app", "app_secret": "production-secret"}
        ),
    )
    read = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(fa_acid_sync, "_read", read)
    with pytest.raises(TimeoutError):
        await fa_acid_sync.run(db)
    read.assert_awaited_once_with("production-app", "production-secret")
    db.execute.assert_not_awaited()
