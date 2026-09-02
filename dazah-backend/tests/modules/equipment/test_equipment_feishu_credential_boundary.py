from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.equipment.feishu import message


@pytest.mark.asyncio
async def test_group_notification_uses_equipment_application(monkeypatch):
    monkeypatch.setattr(
        message,
        "settings",
        SimpleNamespace(
            EQUIPMENT_FEISHU_APP_ID="equipment-app",
            EQUIPMENT_FEISHU_APP_SECRET="equipment-secret",
            FEISHU_EQUIPMENT_CHAT_ID="chat",
        ),
    )
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(message, "_send_group_card", send)
    assert await message.send_claim_notification("WO-1", "worker")
    assert send.await_args.kwargs == {
        "app_id": "equipment-app",
        "app_secret": "equipment-secret",
    }
