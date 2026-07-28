import asyncio
import json
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
)

from app.platform.integrations.feishu import event_handler


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True


@pytest.mark.anyio
async def test_message_callback_does_not_wait_for_agent_processing(monkeypatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    received: list[dict] = []

    async def fake_handle_message_async(**kwargs) -> None:
        received.append(kwargs)
        started.set()
        await release.wait()
        completed.set()

    monkeypatch.setattr(
        event_handler,
        "_handle_message_async",
        fake_handle_message_async,
    )
    event_handler.set_main_loop(asyncio.get_running_loop())

    await asyncio.to_thread(
        event_handler._on_message_receive,
        P2ImMessageReceiveV1(
            {
                "event": {
                    "sender": {
                        "sender_type": "user",
                        "sender_id": {"open_id": "ou_user"},
                    },
                    "message": {
                        "message_type": "text",
                        "message_id": "om_async",
                        "chat_type": "group",
                        "chat_id": "oc_group",
                        "content": '{"text":"@_user_1 测试"}',
                        "mentions": [
                            {
                                "key": "@_user_1",
                                "id": {"open_id": "ou_livzon_bot"},
                                "mentioned_type": "bot",
                                "name": "Livzon 助手",
                            }
                        ],
                    },
                }
            }
        ),
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert completed.is_set() is False
    assert received[0]["chat_id"] == "oc_group"
    assert received[0]["mentions"][0]["id"]["open_id"] == "ou_livzon_bot"
    release.set()
    await asyncio.wait_for(completed.wait(), timeout=1)


@pytest.mark.anyio
async def test_shared_global_app_forwards_private_message_to_livzon(
    monkeypatch,
) -> None:
    import app.core.redis as redis_module

    forwarded: list[dict] = []

    async def fake_uses_shared_app() -> bool:
        return True

    async def fake_forward(**kwargs) -> None:
        forwarded.append(kwargs)

    monkeypatch.setattr(redis_module, "redis_client", FakeRedis())
    monkeypatch.setattr(event_handler, "_uses_shared_livzon_app", fake_uses_shared_app)
    monkeypatch.setattr(
        event_handler,
        "_forward_shared_app_message_to_livzon",
        fake_forward,
    )
    event_handler.set_main_loop(asyncio.get_running_loop())

    await event_handler._handle_message_async(
        msg_type="text",
        message_id="om_shared",
        content='{"text":"你好"}',
        chat_type="p2p",
        chat_id="oc_p2p",
        mentions=[],
        sender_open_id="ou_shared",
        sender_type="user",
    )

    assert forwarded == [
        {
            "msg_type": "text",
            "message_id": "om_shared",
            "content": '{"text":"你好"}',
            "chat_type": "p2p",
            "chat_id": "oc_p2p",
            "mentions": [],
            "sender_open_id": "ou_shared",
            "sender_type": "user",
        }
    ]


@pytest.mark.anyio
async def test_completed_card_action_updates_original_message(monkeypatch) -> None:
    from app.core import config as config_module
    from app.platform.integrations.feishu import im, utils

    updates: list[dict] = []

    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="shared-app",
            FEISHU_APP_SECRET="secret",
        ),
    )

    async def fake_token(app_id: str, app_secret: str, *, cache_key: str) -> str:
        assert (app_id, app_secret) == ("shared-app", "secret")
        assert cache_key == "shared-callback:shared-app"
        return "tenant-token"

    async def fake_update(**kwargs):
        updates.append(kwargs)
        return SimpleNamespace(ok=True, code=0)

    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "update_feishu_message", fake_update)

    card = {"elements": [{"tag": "markdown", "content": "已执行"}]}
    await event_handler._update_callback_message(
        {"_callback_message_id": "om_card", "card": card}
    )

    assert updates == [
        {
            "tenant_access_token": "tenant-token",
            "message_id": "om_card",
            "content": json.dumps(card, ensure_ascii=False),
        }
    ]


@pytest.mark.anyio
async def test_shared_global_app_message_is_deduplicated_before_forward(
    monkeypatch,
) -> None:
    import app.core.redis as redis_module

    forwarded: list[dict] = []

    async def fake_uses_shared_app() -> bool:
        return True

    async def fake_forward(**kwargs) -> None:
        forwarded.append(kwargs)

    monkeypatch.setattr(redis_module, "redis_client", FakeRedis())
    monkeypatch.setattr(event_handler, "_uses_shared_livzon_app", fake_uses_shared_app)
    monkeypatch.setattr(
        event_handler,
        "_forward_shared_app_message_to_livzon",
        fake_forward,
    )
    event_handler.set_main_loop(asyncio.get_running_loop())

    payload = {
        "msg_type": "text",
        "message_id": "om_duplicate",
        "content": '{"text":"你好"}',
        "chat_type": "p2p",
        "chat_id": "oc_p2p",
        "mentions": [],
        "sender_open_id": "ou_shared",
        "sender_type": "user",
    }
    await event_handler._handle_message_async(**payload)
    await event_handler._handle_message_async(**payload)

    assert len(forwarded) == 1


@pytest.mark.anyio
async def test_shared_global_app_forwards_card_action_to_livzon(
    monkeypatch,
) -> None:
    forwarded: list[dict] = []
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def fake_handle_card_action(payload: dict) -> dict:
        forwarded.append(payload)
        started.set()
        await release.wait()
        completed.set()
        return {
            "toast": {"type": "success", "content": "已执行"},
            "card": {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": "已执行"}],
            },
        }

    monkeypatch.setattr(
        event_handler,
        "_handle_card_action_async",
        fake_handle_card_action,
    )
    event_handler.set_main_loop(asyncio.get_running_loop())

    response = await asyncio.to_thread(
        event_handler._on_card_action_trigger,
        P2CardActionTrigger(
            {
                "schema": "2.0",
                "header": {
                    "event_id": "evt_card_shared",
                    "event_type": "card.action.trigger",
                },
                "event": {
                    "operator": {"open_id": "ou_clicker"},
                    "action": {
                        "value": {
                            "action_id": "action_shared",
                            "action_key": "agent_confirmation_execute",
                        }
                    },
                },
            }
        ),
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert completed.is_set() is False
    release.set()
    await asyncio.wait_for(completed.wait(), timeout=1)
    assert response.toast is not None
    assert response.toast.type == "info"
    assert response.toast.content == "操作已受理，正在处理"
    assert response.card is None
    assert forwarded == [
        {
            "schema": "2.0",
            "header": {
                "event_id": "evt_card_shared",
                "event_type": "card.action.trigger",
            },
            "event": {
                "operator": {"open_id": "ou_clicker"},
                "action": {
                    "value": {
                        "action_id": "action_shared",
                        "action_key": "agent_confirmation_execute",
                    }
                },
            },
        }
    ]


def test_event_callbacks_handle_missing_loop_and_background_errors() -> None:
    event_handler._main_loop = None
    response = event_handler._on_card_action_trigger(
        P2CardActionTrigger({"event": {}})
    )
    assert response.toast.type == "error"

    event_handler._on_message_receive(P2ImMessageReceiveV1({}))
    failed = Future()
    failed.set_exception(RuntimeError("background failed"))
    event_handler._log_message_completion(failed)
    event_handler._log_card_action_completion(failed)
    assert event_handler._event_id({"header": {"event_id": "event"}}) == "event"
    assert event_handler._event_id({"header": {}}) is None


@pytest.mark.anyio
async def test_card_action_dispatch_handles_non_livzon_and_failures(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        event_handler,
        "_uses_shared_livzon_app",
        AsyncMock(return_value=False),
    )
    result = await event_handler._handle_card_action_async({})
    assert result["toast"]["type"] == "warning"

    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        SessionContext,
    )
    monkeypatch.setattr(
        event_handler,
        "_uses_shared_livzon_app",
        AsyncMock(return_value=True),
    )
    handler = AsyncMock(
        side_effect=[
            HTTPException(status_code=409, detail="already handled"),
            RuntimeError("database failed"),
        ]
    )
    monkeypatch.setattr(
        "app.platform.identity.service.handle_livzon_feishu_card_action_event",
        handler,
    )

    warning = await event_handler._handle_card_action_async({})
    assert warning["toast"]["content"] == "already handled"
    failure = await event_handler._handle_card_action_async({})
    assert failure["toast"]["type"] == "error"
    assert session.rollback.await_count == 2


@pytest.mark.anyio
async def test_callback_message_update_skips_invalid_and_contains_failures(
    monkeypatch,
) -> None:
    await event_handler._update_callback_message({})
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="app",
            FEISHU_APP_SECRET="secret",
        ),
    )
    token = AsyncMock(return_value="token")
    monkeypatch.setattr(
        "app.platform.integrations.feishu.utils.get_tenant_access_token",
        token,
    )
    update = AsyncMock(return_value=SimpleNamespace(ok=False, code=500))
    monkeypatch.setattr(
        "app.platform.integrations.feishu.im.update_feishu_message",
        update,
    )
    payload = {
        "_callback_message_id": "message",
        "card": {"elements": []},
    }
    await event_handler._update_callback_message(payload)
    token.side_effect = RuntimeError("token failed")
    await event_handler._update_callback_message(payload)
    assert update.await_count == 1


@pytest.mark.anyio
async def test_shared_app_detection_uses_config_and_fallback(monkeypatch) -> None:
    session = object()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        SessionContext,
    )
    get_active = AsyncMock(
        side_effect=[
            SimpleNamespace(app_id="global"),
            SimpleNamespace(app_id="other"),
            None,
        ]
    )
    monkeypatch.setattr(
        "app.platform.identity.repository.FeishuConfigRepository.get_active",
        get_active,
    )

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="",
            LIVZON_FEISHU_EVENT_WS_ENABLED=False,
            LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=False,
        ),
    )
    assert not await event_handler._uses_shared_livzon_app()

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="global",
            LIVZON_FEISHU_EVENT_WS_ENABLED=True,
            LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=False,
        ),
    )
    assert await event_handler._uses_shared_livzon_app()
    assert not await event_handler._uses_shared_livzon_app()
    assert await event_handler._uses_shared_livzon_app()


@pytest.mark.anyio
async def test_forward_shared_message_commits_or_rolls_back(monkeypatch) -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        SessionContext,
    )
    handler = AsyncMock(
        side_effect=[
            {"status": "accepted"},
            RuntimeError("handler failed"),
        ]
    )
    monkeypatch.setattr(
        "app.platform.identity.service.handle_livzon_feishu_message_receive_event",
        handler,
    )
    kwargs = {
        "msg_type": "text",
        "message_id": "message",
        "content": "{}",
        "chat_type": "p2p",
        "chat_id": "chat",
        "mentions": [],
        "sender_open_id": "open",
        "sender_type": "user",
    }
    await event_handler._forward_shared_app_message_to_livzon(**kwargs)
    await event_handler._forward_shared_app_message_to_livzon(**kwargs)
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()


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
