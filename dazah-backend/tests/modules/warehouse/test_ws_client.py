from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.warehouse import ws_client


@pytest.mark.anyio
async def test_restart_skips_duplicate_consumer_for_hermes_owned_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subscribed_tokens: list[str] = []
    started: list[str] = []

    class FakeWarehouseFeishuClient:
        def __init__(
            self: Any,
            *,
            app_id: str,
            app_secret: str,
            app_token: str,
        ) -> None:
            assert app_id == "cli_shared_app"
            assert app_secret == "test-secret"
            subscribed_tokens.append(app_token)

        async def subscribe_bitable(self: Any) -> None:
            return None

    monkeypatch.setattr(ws_client, "_main_loop", object())
    monkeypatch.setattr(ws_client, "WarehouseFeishuClient", FakeWarehouseFeishuClient)
    monkeypatch.setattr(
        ws_client,
        "_is_hermes_owned_app",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(ws_client, "stop_ws_client", lambda _name: None)
    monkeypatch.setattr(
        ws_client,
        "start_ws_client",
        lambda **_kwargs: started.append("started"),
    )

    status = await ws_client.restart_ws_with_config(
        app_id="cli_shared_app",
        app_secret="test-secret",
        app_tokens={"warehouse": "app_token_1"},
    )

    assert subscribed_tokens == ["app_token_1"]
    assert started == []
    assert status.enabled is True
    assert status.connected is True
