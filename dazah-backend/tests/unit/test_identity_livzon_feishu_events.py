import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.platform.identity import service
from app.platform.identity.models import FeishuConfig, User


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []

    async def flush(self) -> None:
        return None

    def add(self, item: object) -> None:
        self.added.append(item)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True


class FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user

    async def get_by_feishu_open_id(self, db, open_id: str) -> User | None:
        if self.user and self.user.feishu_open_id == open_id:
            return self.user
        return None

    async def get_by_id(self, db, user_id: uuid.UUID) -> User | None:
        if self.user and self.user.id == user_id:
            return self.user
        return None


class FakeCardActionRepository:
    def __init__(self, action=None) -> None:
        self.action = action
        self.created: list[SimpleNamespace] = []

    async def create(self, db, **kwargs):
        action = SimpleNamespace(id=uuid.uuid4(), status="pending", **kwargs)
        self.created.append(action)
        return action

    async def get_pending_by_id(self, db, action_id):
        if self.action and str(self.action.id) == str(action_id):
            return self.action
        return None

    async def get_by_id_for_update(self, db, action_id):
        return await self.get_pending_by_id(db, action_id)

    async def set_message_id_for_card(self, db, *, card_id, message_id) -> None:
        return None


class FakeConfigRepository:
    def __init__(self, config: FeishuConfig) -> None:
        self.config = config

    async def get_active(self, db) -> FeishuConfig:
        return self.config


def _user(open_id: str = "ou_test") -> User:
    return User(
        id=uuid.uuid4(),
        name="飞书测试用户",
        feishu_open_id=open_id,
        status="active",
        is_deleted=False,
    )


def _message_event(
    *,
    message_id: str = "om_test",
    message_type: str = "text",
    chat_type: str = "p2p",
    text: str = "查询今日库存",
    mentions: list[dict] | None = None,
) -> dict:
    content = json.dumps({"text": text}, ensure_ascii=False)
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou_test"},
            },
            "message": {
                "message_id": message_id,
                "chat_type": chat_type,
                "chat_id": "oc_group" if chat_type != "p2p" else "oc_p2p",
                "message_type": message_type,
                "content": content,
                "mentions": mentions or [],
            },
        },
    }


@pytest.mark.anyio
async def test_private_text_message_is_deduplicated_and_audited(monkeypatch) -> None:
    import app.core.redis as redis_module
    import app.modules.agent.public_api as agent_public_api

    user = _user()
    redis = FakeRedis()
    replies: list[tuple[str, bool]] = []
    agent_calls: list[dict] = []
    status_events: list[tuple[str, object]] = []

    async def fake_acquire_lock(key: str, timeout: int) -> bool:
        return True

    async def fake_release_lock(key: str) -> None:
        return None

    async def fake_reply(
        db,
        *,
        open_id: str,
        text: str,
        markdown: bool = False,
        reply_to_message_id: str | None = None,
    ) -> bool:
        replies.append((text, markdown))
        return True

    async def fake_agent(db, **kwargs):
        agent_calls.append(kwargs)
        return SimpleNamespace(
            text="库存充足。",
            session_id=uuid.uuid4(),
            pending_confirmations=(),
        )

    async def fake_confirmation_cards(*args, **kwargs) -> None:
        return None

    async def fake_start_reply(db, *, message_id: str) -> str:
        status_events.append(("start", message_id))
        return "reaction_typing"

    async def fake_finish_reply(db, **kwargs) -> bool:
        status_events.append(("finish", kwargs))
        return True

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(service, "_send_livzon_feishu_text_to_open_id", fake_reply)
    monkeypatch.setattr(service, "_start_livzon_feishu_message_reply", fake_start_reply)
    monkeypatch.setattr(
        service,
        "_finish_livzon_feishu_message_reply",
        fake_finish_reply,
    )
    monkeypatch.setattr(
        service,
        "_send_livzon_agent_confirmation_cards",
        fake_confirmation_cards,
    )
    monkeypatch.setattr(redis_module, "redis_client", redis)
    monkeypatch.setattr(redis_module, "acquire_lock", fake_acquire_lock)
    monkeypatch.setattr(redis_module, "release_lock", fake_release_lock)
    monkeypatch.setattr(agent_public_api, "handle_feishu_direct_message", fake_agent)

    db = FakeDb()
    first = await service.handle_livzon_feishu_message_receive_event(
        db, payload=_message_event()
    )
    second = await service.handle_livzon_feishu_message_receive_event(
        db, payload=_message_event()
    )

    assert first["status"] == "processed"
    assert second == {"status": "duplicate"}
    assert len(agent_calls) == 1
    assert status_events == [
        ("start", "om_test"),
        (
            "finish",
            {
                "message_id": "om_test",
                "processing_reaction_id": "reaction_typing",
                "completed": True,
            },
        ),
    ]
    assert replies == [("库存充足。", True)]
    assert any(
        getattr(item, "action", "") == "feishu_agent_message"
        for item in db.added
    )


@pytest.mark.anyio
async def test_group_message_without_livzon_mention_is_ignored(monkeypatch) -> None:
    import app.modules.agent.public_api as agent_public_api

    async def fail_bot_identity(*args, **kwargs):
        raise AssertionError("messages without mentions must not resolve bot identity")

    async def fail_agent(*args, **kwargs):
        raise AssertionError("unmentioned group messages must not reach Agent")

    monkeypatch.setattr(
        service,
        "_active_livzon_feishu_bot_open_id",
        fail_bot_identity,
    )
    monkeypatch.setattr(agent_public_api, "handle_feishu_direct_message", fail_agent)

    result = await service.handle_livzon_feishu_message_receive_event(
        FakeDb(),
        payload=_message_event(
            message_id="om_group_unmentioned",
            chat_type="group",
            text="查询今日库存",
        ),
    )

    assert result == {"status": "ignored"}


@pytest.mark.anyio
async def test_group_message_replies_only_when_livzon_is_mentioned(
    monkeypatch,
) -> None:
    import app.core.redis as redis_module
    import app.modules.agent.public_api as agent_public_api

    user = _user()
    replies: list[dict] = []
    agent_calls: list[dict] = []

    async def fake_bot_open_id(db) -> str:
        return "ou_livzon_bot"

    async def fake_acquire_lock(key: str, timeout: int) -> bool:
        assert key == "livzon:feishu:conversation:oc_group"
        return True

    async def fake_release_lock(key: str) -> None:
        assert key == "livzon:feishu:conversation:oc_group"

    async def fake_reply(db, **kwargs) -> bool:
        replies.append(kwargs)
        return True

    async def fake_agent(db, **kwargs):
        agent_calls.append(kwargs)
        return SimpleNamespace(
            text="库存充足。",
            session_id=uuid.uuid4(),
            pending_confirmations=(),
        )

    async def fake_start_reply(db, *, message_id: str) -> str:
        return "reaction_typing"

    async def fake_finish_reply(db, **kwargs) -> bool:
        return True

    async def fake_confirmation_cards(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(
        service,
        "_active_livzon_feishu_bot_open_id",
        fake_bot_open_id,
    )
    monkeypatch.setattr(service, "_send_livzon_feishu_text_to_open_id", fake_reply)
    monkeypatch.setattr(service, "_start_livzon_feishu_message_reply", fake_start_reply)
    monkeypatch.setattr(
        service,
        "_finish_livzon_feishu_message_reply",
        fake_finish_reply,
    )
    monkeypatch.setattr(
        service,
        "_send_livzon_agent_confirmation_cards",
        fake_confirmation_cards,
    )
    monkeypatch.setattr(redis_module, "redis_client", FakeRedis())
    monkeypatch.setattr(redis_module, "acquire_lock", fake_acquire_lock)
    monkeypatch.setattr(redis_module, "release_lock", fake_release_lock)
    monkeypatch.setattr(agent_public_api, "handle_feishu_direct_message", fake_agent)

    result = await service.handle_livzon_feishu_message_receive_event(
        FakeDb(),
        payload=_message_event(
            message_id="om_group_mentioned",
            chat_type="group",
            text="@_user_1 查询今日库存",
            mentions=[
                {
                    "key": "@_user_1",
                    "id": {"open_id": "ou_livzon_bot"},
                    "mentioned_type": "bot",
                    "name": "Livzon 助手",
                }
            ],
        ),
    )

    assert result["status"] == "processed"
    assert agent_calls[0]["text"] == "查询今日库存"
    assert agent_calls[0]["conversation_peer_id"] == "oc_group"
    assert replies == [
        {
            "open_id": "ou_test",
            "text": "库存充足。",
            "markdown": True,
            "reply_to_message_id": "om_group_mentioned",
        }
    ]


@pytest.mark.anyio
async def test_non_text_private_message_is_deduplicated_without_agent_call(
    monkeypatch,
) -> None:
    import app.core.redis as redis_module
    import app.modules.agent.public_api as agent_public_api

    redis = FakeRedis()
    replies: list[str] = []

    async def fake_reply(
        db,
        *,
        open_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> bool:
        replies.append(text)
        return True

    async def fail_agent(*args, **kwargs):
        raise AssertionError("non-text messages must not reach Agent")

    monkeypatch.setattr(service, "_send_livzon_feishu_text_to_open_id", fake_reply)
    monkeypatch.setattr(redis_module, "redis_client", redis)
    monkeypatch.setattr(agent_public_api, "handle_feishu_direct_message", fail_agent)

    first = await service.handle_livzon_feishu_message_receive_event(
        FakeDb(), payload=_message_event(message_type="image")
    )
    second = await service.handle_livzon_feishu_message_receive_event(
        FakeDb(), payload=_message_event(message_type="image")
    )

    assert first == {"status": "unsupported"}
    assert second == {"status": "duplicate"}
    assert len(replies) == 1


@pytest.mark.anyio
async def test_message_reply_status_transitions_from_typing_to_ok(monkeypatch) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    calls: list[dict] = []

    async def fake_credentials(db) -> tuple[str, str]:
        return "cli_test", "app-secret"

    async def fake_token(app_id: str, app_secret: str, *, cache_key: str) -> str:
        assert (app_id, app_secret) == ("cli_test", "app-secret")
        assert cache_key == "livzon-assistant:cli_test"
        return "tenant-token"

    async def fake_create_reaction(**kwargs):
        calls.append({"action": "create", **kwargs})
        return im.FeishuMessageReactionResult(
            ok=True,
            reaction_id=(
                "reaction_typing"
                if kwargs["emoji_type"] == "Typing"
                else "reaction_ok"
            ),
            code=0,
        )

    async def fake_delete_reaction(**kwargs):
        calls.append({"action": "delete", **kwargs})
        return im.FeishuMessageReactionResult(ok=True, code=0)

    monkeypatch.setattr(service, "_active_livzon_feishu_credentials", fake_credentials)
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "create_feishu_message_reaction", fake_create_reaction)
    monkeypatch.setattr(im, "delete_feishu_message_reaction", fake_delete_reaction)

    processing_reaction_id = await service._start_livzon_feishu_message_reply(
        FakeDb(),
        message_id="om_read",
    )
    marked = await service._finish_livzon_feishu_message_reply(
        FakeDb(),
        message_id="om_read",
        processing_reaction_id=processing_reaction_id,
        completed=True,
    )

    assert marked is True
    assert calls == [
        {
            "action": "create",
            "tenant_access_token": "tenant-token",
            "message_id": "om_read",
            "emoji_type": "Typing",
        },
        {
            "action": "delete",
            "tenant_access_token": "tenant-token",
            "message_id": "om_read",
            "reaction_id": "reaction_typing",
        },
        {
            "action": "create",
            "tenant_access_token": "tenant-token",
            "message_id": "om_read",
            "emoji_type": "OK",
        },
    ]


@pytest.mark.anyio
async def test_livzon_credentials_fall_back_to_global_event_app(monkeypatch) -> None:
    class EmptyConfigRepository:
        async def get_active(self, db):
            return None

    monkeypatch.setattr(service, "_feishu_config_repo", EmptyConfigRepository())
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            LIVZON_FEISHU_EVENT_WS_ENABLED=True,
            LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=False,
            FEISHU_APP_ID="global-app",
            FEISHU_APP_SECRET="global-secret",
        ),
    )

    credentials = await service._active_livzon_feishu_credentials(FakeDb())

    assert credentials == ("global-app", "global-secret")


@pytest.mark.anyio
async def test_agent_reply_delivery_failure_is_not_reported_as_processed(
    monkeypatch,
) -> None:
    import app.core.redis as redis_module
    import app.modules.agent.public_api as agent_public_api

    user = _user()

    async def fake_acquire_lock(key: str, timeout: int) -> bool:
        return True

    async def fake_release_lock(key: str) -> None:
        return None

    async def fake_start_reply(db, *, message_id: str) -> str:
        return "reaction_typing"

    finish_calls: list[dict] = []

    async def fake_finish_reply(db, **kwargs) -> bool:
        finish_calls.append(kwargs)
        return True

    async def fake_reply(*args, **kwargs) -> bool:
        return False

    async def fake_agent(db, **kwargs):
        return SimpleNamespace(
            text="已生成但无法发送的回复",
            session_id=uuid.uuid4(),
            pending_confirmations=(),
        )

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(service, "_start_livzon_feishu_message_reply", fake_start_reply)
    monkeypatch.setattr(
        service,
        "_finish_livzon_feishu_message_reply",
        fake_finish_reply,
    )
    monkeypatch.setattr(service, "_send_livzon_feishu_text_to_open_id", fake_reply)
    monkeypatch.setattr(redis_module, "redis_client", FakeRedis())
    monkeypatch.setattr(redis_module, "acquire_lock", fake_acquire_lock)
    monkeypatch.setattr(redis_module, "release_lock", fake_release_lock)
    monkeypatch.setattr(agent_public_api, "handle_feishu_direct_message", fake_agent)

    db = FakeDb()
    result = await service.handle_livzon_feishu_message_receive_event(
        db,
        payload=_message_event(message_id="om_reply_failed"),
    )

    assert result["status"] == "reply_failed"
    assert finish_calls == [
        {
            "message_id": "om_reply_failed",
            "processing_reaction_id": "reaction_typing",
            "completed": False,
        }
    ]
    assert any(
        getattr(item, "new_value", {}).get("outcome") == "reply_failed"
        for item in db.added
    )


@pytest.mark.anyio
async def test_agent_reply_uses_interactive_markdown_card(monkeypatch) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="encrypted-secret",
        is_active=True,
    )
    sent_messages: list[dict] = []

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        sent_messages.append(kwargs)
        return im.FeishuMessageSendResult(ok=True, message_id="om_reply", code=0)

    monkeypatch.setattr(service, "_feishu_config_repo", FakeConfigRepository(config))
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    sent = await service._send_livzon_feishu_text_to_open_id(
        FakeDb(),
        open_id="ou_test",
        text="## 汇总\n\n**重点**\n\n---\n\n- 第一项",
        markdown=True,
    )

    assert sent is True
    assert sent_messages[0]["msg_type"] == "interactive"
    card = json.loads(sent_messages[0]["content"])
    assert card["elements"][0]["tag"] == "markdown"
    assert card["elements"][0]["content"].startswith("**汇总**")
    assert "**重点**" in card["elements"][0]["content"]
    assert card["elements"][1] == {"tag": "hr"}
    assert card["elements"][2]["content"] == "- 第一项"


@pytest.mark.anyio
async def test_agent_confirmation_card_uses_confirmation_expiry(monkeypatch) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    user = _user()
    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="encrypted-secret",
        card_callback_verification_token="verify-token",
        is_active=True,
    )
    actions = FakeCardActionRepository()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        return im.FeishuMessageSendResult(ok=True, message_id="om_card", code=0)

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(service, "_feishu_config_repo", FakeConfigRepository(config))
    monkeypatch.setattr(service, "_feishu_card_action_repo", actions)
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    await service._send_livzon_agent_confirmation_cards(
        FakeDb(),
        user=user,
        confirmations=(
            SimpleNamespace(
                id=uuid.uuid4(),
                summary="创建采购申请",
                risk_level="medium",
                expires_at=expires_at,
            ),
        ),
    )

    assert len(actions.created) == 2
    assert {item.action_key for item in actions.created} == {
        "agent_confirmation_execute",
        "agent_confirmation_cancel",
    }
    assert all(item.expires_at == expires_at for item in actions.created)


@pytest.mark.anyio
async def test_failed_confirmation_card_delivery_disables_its_actions(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    user = _user()
    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="encrypted-secret",
        card_callback_verification_token="verify-token",
        is_active=True,
    )
    actions = FakeCardActionRepository()

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        return im.FeishuMessageSendResult(
            ok=False,
            code=230001,
            error_message="recipient unavailable",
        )

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(service, "_feishu_config_repo", FakeConfigRepository(config))
    monkeypatch.setattr(service, "_feishu_card_action_repo", actions)
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    result = await service._send_livzon_feishu_callback_card(
        FakeDb(),
        user_ids=[user.id],
        title="Livzon 助手操作确认",
        markdown="确认创建采购申请",
        header_template="orange",
        actions=[{"action_key": "agent_confirmation_execute", "label": "确认执行"}],
        business_ref={
            "kind": "agent_confirmation",
            "confirmation_id": str(uuid.uuid4()),
        },
    )

    assert result["failed_count"] == 1
    assert all(item.status == "failed" for item in actions.created)


@pytest.mark.anyio
async def test_agent_confirmation_card_executes_only_for_recipient(monkeypatch) -> None:
    import app.modules.agent.public_api as agent_public_api

    user = _user("ou_recipient")
    confirmation_id = uuid.uuid4()
    action = SimpleNamespace(
        id=uuid.uuid4(),
        card_id="livzon-card",
        message_id="om_card",
        local_user_id=user.id,
        recipient_open_id=user.feishu_open_id,
        business_ref={
            "kind": "agent_confirmation",
            "confirmation_id": str(confirmation_id),
            "summary": "创建采购申请",
        },
        action_key="agent_confirmation_execute",
        action_label="确认执行",
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        clicked_open_id=None,
        callback_summary=None,
    )
    executed: list[uuid.UUID] = []

    async def fake_execute(db, *, confirmation_id: uuid.UUID, user: User):
        executed.append(confirmation_id)
        return (
            SimpleNamespace(
                id=confirmation_id,
                summary="创建采购申请",
                status="executed",
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr(service, "_repo", FakeUserRepository(user))
    monkeypatch.setattr(
        service,
        "_feishu_card_action_repo",
        FakeCardActionRepository(action),
    )
    monkeypatch.setattr(agent_public_api, "execute_feishu_confirmation", fake_execute)

    result = await service.handle_livzon_feishu_card_action_event(
        FakeDb(),
        payload={
            "event": {
                "operator": {"open_id": "ou_recipient"},
                "action": {
                    "value": {
                        "action_id": str(action.id),
                        "action_key": "agent_confirmation_execute",
                    }
                },
            }
        },
    )

    assert executed == [confirmation_id]
    assert action.status == "processed"
    assert result["toast"]["type"] == "success"
    assert result["_callback_message_id"] == "om_card"
