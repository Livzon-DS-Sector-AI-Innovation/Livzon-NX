from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.warehouse import ws_client
from app.modules.warehouse.schemas import WarehouseFeishuWsStatus


@pytest.mark.parametrize("valid", [True, False])
async def test_db_ws_bindings_accept_only_nonempty_tokens_in_original_order(
    monkeypatch: pytest.MonkeyPatch, valid: bool
) -> None:
    from app.modules.warehouse.repository import WarehouseRepository

    @asynccontextmanager
    async def fake_session() -> AsyncIterator[None]:
        yield None

    tokens = (
        [None, "", 12, False, "base-first", "base-first", "base-second"]
        if valid
        else [None, "", 12, False]
    )
    config = SimpleNamespace(app_id="test-app", encrypted_app_secret="test-encrypted")
    monkeypatch.setattr(ws_client, "_main_loop", object())
    monkeypatch.setattr(ws_client, "async_session_factory", fake_session)
    monkeypatch.setattr(
        WarehouseRepository, "get_active_feishu_config", AsyncMock(return_value=config)
    )
    monkeypatch.setattr(
        WarehouseRepository,
        "list_page_feishu_configs",
        AsyncMock(return_value=[{"app_token": token} for token in tokens]),
    )
    monkeypatch.setattr("app.core.secrets.decrypt_secret", lambda _value: "test-secret")
    restart = AsyncMock(return_value=WarehouseFeishuWsStatus(enabled=True))
    stop = AsyncMock()
    monkeypatch.setattr(ws_client, "restart_ws_with_config", restart)
    monkeypatch.setattr(ws_client, "stop_ws", stop)
    monkeypatch.setattr(
        ws_client, "get_ws_status", AsyncMock(return_value=WarehouseFeishuWsStatus())
    )
    status = await ws_client.start_ws_from_db()
    if valid:
        assert status.enabled is True
        assert restart.await_args.kwargs["app_tokens"] == {
            "source_1": "base-first",
            "source_2": "base-second",
        }
        stop.assert_not_awaited()
    else:
        assert status.enabled is False
        stop.assert_awaited_once()
        restart.assert_not_awaited()


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
