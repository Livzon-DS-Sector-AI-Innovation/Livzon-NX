from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu import event_handler


@pytest.mark.anyio
async def test_bitable_change_handler_publishes_event(monkeypatch) -> None:
    publish = AsyncMock()
    monkeypatch.setattr(event_handler.event_bus, "publish", publish)

    await event_handler._handle_bitable_record_changed_async(
        file_token="app",
        table_id="table",
        revision=2,
        update_time=123,
        actions=[{"record_id": "record", "action": "edit"}],
    )

    publish.assert_awaited_once()
