import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity import agent_tools, service
from app.platform.identity.models import FeishuConfig, User


class FakeDb:
    def __init__(self) -> None:
        self.added = []

    async def get(self, model, item_id):
        return None

    async def flush(self) -> None:
        return None

    def add(self, item) -> None:
        self.added.append(item)


def test_unified_feishu_message_uses_confirmation_not_human_decision_refusal() -> None:
    ensure_agent_tools_registered()
    spec = tool_registry.require("identity.send_feishu_message")

    assert spec.write is True
    assert spec.risk_level == "medium"
    assert spec.human_decision_required is False


class FakeFeishuConfigRepo:
    def __init__(self, config: FeishuConfig | None) -> None:
        self.config = config

    async def get_active(self, db) -> FeishuConfig | None:
        return self.config


class FakeUserRepo:
    def __init__(self, users: list[User]) -> None:
        self.users = {user.id: user for user in users}

    async def get_by_id(self, db, user_id):
        return self.users.get(user_id)


class FakeRecipientRepo:
    def __init__(self, mapping: dict[str, list[User]]) -> None:
        self.mapping = mapping

    async def find_by_livzon_recipient_identifier(self, db, identifier):
        return self.mapping.get(identifier, [])


class FakeCardActionRepo:
    def __init__(self, action=None) -> None:
        self.action = action
        self.created = []
        self.updated_cards = []

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

    async def set_message_id_for_card(self, db, *, card_id, message_id):
        self.updated_cards.append((card_id, message_id))


class FakeRepo:
    def __init__(self) -> None:
        self.tool_calls = []
        self.confirmations = []

    async def get_session(self, db, session_id):
        return None

    async def create_tool_call(self, db, *, session_id, operation, request_payload):
        call = SimpleNamespace(status="started", error_message=None)
        self.tool_calls.append(call)
        return call

    async def finish_tool_call(
        self,
        db,
        call,
        *,
        status,
        response_payload=None,
        error_message=None,
    ):
        call.status = status
        call.response_payload = response_payload
        call.error_message = error_message
        return call

    async def create_confirmation(
        self,
        db,
        *,
        session_id,
        user_id,
        operation,
        summary,
        risk_level,
        request_payload,
        expires_at,
    ):
        confirmation = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            operation=operation,
            summary=summary,
            risk_level=risk_level,
            status="pending",
            request_payload=request_payload,
            expires_at=expires_at,
        )
        self.confirmations.append(confirmation)
        return confirmation


def _config() -> FeishuConfig:
    return FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="encrypted-secret",
        is_active=True,
    )


def _callback_config() -> FeishuConfig:
    config = _config()
    config.card_callback_verification_token = "verify-token"
    return config


def _user(
    *,
    name: str,
    open_id: str | None,
    user_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        name=name,
        feishu_open_id=open_id,
        status="active",
        is_deleted=False,
    )


@pytest.mark.anyio
async def test_send_livzon_feishu_message_requires_livzon_config(
    monkeypatch,
) -> None:
    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(None))

    with pytest.raises(HTTPException) as exc_info:
        await service.send_livzon_feishu_text_message(
            FakeDb(),
            user_ids=[uuid.uuid4()],
            text="测试消息",
        )

    assert exc_info.value.status_code == 400
    assert "Livzon 助手飞书" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_send_livzon_feishu_text_message_uses_local_open_id(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    user = _user(name="张三", open_id="ou_123")
    sent_payloads = []

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        sent_payloads.append(kwargs)
        return im.FeishuMessageSendResult(ok=True, message_id="om_1", code=0)

    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(_config()))
    monkeypatch.setattr(service, "_repo", FakeUserRepo([user]))
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    result = await service.send_livzon_feishu_text_message(
        FakeDb(),
        user_ids=[user.id],
        text="测试消息",
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert sent_payloads[0]["tenant_access_token"] == "tenant-token"
    assert sent_payloads[0]["receive_id"] == "ou_123"
    assert sent_payloads[0]["msg_type"] == "text"
    assert json.loads(sent_payloads[0]["content"]) == {"text": "测试消息"}


@pytest.mark.anyio
async def test_send_livzon_feishu_message_skips_user_without_open_id(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    user = _user(name="李四", open_id=None)
    send_calls = []

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        send_calls.append(kwargs)
        return im.FeishuMessageSendResult(ok=True, message_id="om_1", code=0)

    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(_config()))
    monkeypatch.setattr(service, "_repo", FakeUserRepo([user]))
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    result = await service.send_livzon_feishu_text_message(
        FakeDb(),
        user_ids=[user.id],
        text="测试消息",
    )

    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert "feishu_open_id" in result["results"][0]["error_message"]
    assert send_calls == []


@pytest.mark.anyio
async def test_send_livzon_feishu_card_message_builds_interactive_card(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    user = _user(name="王五", open_id="ou_456")
    sent_payloads = []

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        sent_payloads.append(kwargs)
        return im.FeishuMessageSendResult(ok=True, message_id="om_2", code=0)

    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(_config()))
    monkeypatch.setattr(service, "_repo", FakeUserRepo([user]))
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    result = await service.send_livzon_feishu_card_message(
        FakeDb(),
        user_ids=[user.id],
        title="通知",
        markdown="**请处理**",
        header_template="green",
        button_text="查看详情",
        button_url="https://example.com/ticket/1",
    )

    card = json.loads(sent_payloads[0]["content"])
    assert result["success_count"] == 1
    assert sent_payloads[0]["msg_type"] == "interactive"
    assert card["header"]["template"] == "green"
    assert card["header"]["title"]["content"] == "通知"
    assert card["elements"][0]["content"] == "**请处理**"
    assert card["elements"][1]["actions"][0]["url"] == "https://example.com/ticket/1"


@pytest.mark.anyio
async def test_unified_feishu_message_routes_low_value_short_text(monkeypatch) -> None:
    calls = []

    async def fake_text(db, *, user_ids, text):
        calls.append(("text", user_ids, text))
        return {"total": 1, "success_count": 1, "failed_count": 0, "results": []}

    monkeypatch.setattr(service, "send_livzon_feishu_text_message", fake_text)

    result = await service.send_livzon_feishu_message(
        FakeDb(),
        user_ids=[uuid.uuid4()],
        text="短通知",
        value_level="low",
        structured=False,
        requires_business_action=False,
    )

    assert result["message_form"] == "text"
    assert calls[0][0] == "text"


@pytest.mark.anyio
async def test_unified_feishu_message_routes_structured_card(monkeypatch) -> None:
    calls = []

    async def fake_card(db, **kwargs):
        calls.append(kwargs)
        return {"total": 1, "success_count": 1, "failed_count": 0, "results": []}

    monkeypatch.setattr(service, "send_livzon_feishu_card_message", fake_card)

    result = await service.send_livzon_feishu_message(
        FakeDb(),
        user_ids=[uuid.uuid4()],
        text="库存汇总",
        title="库存汇总",
        markdown="- A: 1",
        value_level="medium",
        structured=True,
    )

    assert result["message_form"] == "card"
    assert calls[0]["title"] == "库存汇总"


@pytest.mark.anyio
async def test_unified_feishu_message_honors_an_explicit_card_request(
    monkeypatch,
) -> None:
    calls = []

    async def fake_card(db, **kwargs):
        calls.append(kwargs)
        return {"total": 1, "success_count": 1, "failed_count": 0, "results": []}

    monkeypatch.setattr(service, "send_livzon_feishu_card_message", fake_card)

    result = await service.send_livzon_feishu_message(
        FakeDb(),
        user_ids=[uuid.uuid4()],
        text="3条草稿采购申请汇总",
        title="采购申请汇总",
        markdown="共 3 条草稿采购申请",
        value_level="low",
        structured=False,
        message_form="card",
    )

    assert result["message_form"] == "card"
    assert calls[0]["title"] == "采购申请汇总"


@pytest.mark.anyio
async def test_unified_feishu_message_rejects_forced_wrong_shape() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await service.send_livzon_feishu_message(
            FakeDb(),
            user_ids=[uuid.uuid4()],
            text="请处理",
            value_level="high",
            structured=True,
            requires_business_action=True,
            message_form="text",
        )

    assert exc_info.value.status_code == 400
    assert "interactive_card" in str(exc_info.value.detail)


def test_build_callback_card_content_has_controlled_values() -> None:
    from app.platform.integrations.feishu.im import build_callback_card_content

    card = json.loads(
        build_callback_card_content(
            title="待处理",
            markdown="请处理库存异常",
            actions=[
                {
                    "action_id": str(uuid.uuid4()),
                    "action_key": "start_processing",
                    "label": "开始处理",
                }
            ],
        )
    )

    button = card["elements"][1]["actions"][0]
    assert button["tag"] == "button"
    assert button["value"]["action_key"] == "start_processing"
    assert "confirm" in button


def test_build_markdown_card_content_renders_common_agent_markdown() -> None:
    from app.platform.integrations.feishu.im import build_markdown_card_content

    card = json.loads(
        build_markdown_card_content(
            title="Livzon 助手",
            markdown=(
                "## 📋 采购清单\n\n"
                "**重点**\n\n---\n\n"
                "- [x] 第一项\n"
                "- [ ] 第二项\n\n"
                "[查看详情](https://example.com/detail)"
            ),
        )
    )

    assert card["header"]["title"]["content"] == "Livzon 助手"
    assert card["elements"] == [
        {
            "tag": "markdown",
            "content": "**📋 采购清单**\n\n**重点**",
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": (
                "- ☑ 第一项\n"
                "- ☐ 第二项\n\n"
                "<a href='https://example.com/detail'>查看详情</a>"
            ),
        },
    ]


@pytest.mark.anyio
async def test_callback_card_requires_callback_config(monkeypatch) -> None:
    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(_config()))
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.send_livzon_feishu_message(
            FakeDb(),
            user_ids=[uuid.uuid4()],
            text="请处理",
            requires_business_action=True,
        )

    assert exc_info.value.status_code == 400
    assert "Verification Token" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_callback_action_updates_status_and_writes_audit(monkeypatch) -> None:
    action = SimpleNamespace(
        id=uuid.uuid4(),
        card_id="card_1",
        message_id="om_1",
        local_user_id=uuid.uuid4(),
        recipient_open_id="ou_clicker",
        action_key="mark_done",
        action_label="标记完成",
        status="pending",
        expires_at=None,
        clicked_open_id=None,
        callback_summary=None,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(_callback_config()),
    )
    monkeypatch.setattr(service, "_feishu_card_action_repo", FakeCardActionRepo(action))
    monkeypatch.setattr(
        service,
        "_repo",
        FakeUserRepo(
            [_user(name="点击用户", open_id="ou_clicker", user_id=action.local_user_id)]
        ),
    )
    db = FakeDb()

    result = await service.handle_livzon_feishu_card_callback(
        db,
        payload={
            "token": "verify-token",
            "event": {
                "operator": {"open_id": "ou_clicker"},
                "action": {
                    "value": {
                        "action_id": str(action.id),
                        "action_key": "mark_done",
                    }
                },
            },
        },
        raw_body=b"{}",
    )

    assert action.status == "processed"
    assert action.clicked_open_id == "ou_clicker"
    assert result["toast"]["type"] == "success"
    assert result["_callback_message_id"] == "om_1"
    assert result["card"]["header"]["template"] == "green"
    assert db.added


@pytest.mark.anyio
async def test_ws_card_action_updates_without_callback_token(monkeypatch) -> None:
    action = SimpleNamespace(
        id=uuid.uuid4(),
        card_id="card_1",
        message_id="om_1",
        local_user_id=uuid.uuid4(),
        recipient_open_id="ou_clicker",
        action_key="start_processing",
        action_label="开始处理",
        status="pending",
        expires_at=None,
        clicked_open_id=None,
        callback_summary=None,
    )
    monkeypatch.setattr(service, "_feishu_card_action_repo", FakeCardActionRepo(action))
    monkeypatch.setattr(
        service,
        "_repo",
        FakeUserRepo(
            [_user(name="点击用户", open_id="ou_clicker", user_id=action.local_user_id)]
        ),
    )
    db = FakeDb()

    result = await service.handle_livzon_feishu_card_action_event(
        db,
        payload={
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_clicker"},
                "action": {
                    "value": {
                        "action_id": str(action.id),
                        "action_key": "start_processing",
                    }
                },
            },
        },
    )

    assert action.status == "processed"
    assert action.clicked_open_id == "ou_clicker"
    assert result["toast"]["type"] == "success"
    assert db.added


@pytest.mark.anyio
async def test_callback_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(_callback_config()),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.handle_livzon_feishu_card_callback(
            FakeDb(),
            payload={"token": "bad-token", "challenge": "abc"},
            raw_body=b"{}",
        )

    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_callback_duplicate_click_is_idempotent(monkeypatch) -> None:
    action = SimpleNamespace(
        id=uuid.uuid4(),
        card_id="card_1",
        message_id="om_1",
        local_user_id=uuid.uuid4(),
        recipient_open_id="ou_1",
        action_key="acknowledge",
        action_label="已知悉",
        status="processed",
        expires_at=None,
        clicked_open_id="ou_old",
        callback_summary=None,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(_callback_config()),
    )
    monkeypatch.setattr(service, "_feishu_card_action_repo", FakeCardActionRepo(action))
    monkeypatch.setattr(
        service,
        "_repo",
        FakeUserRepo(
            [_user(name="点击用户", open_id="ou_1", user_id=action.local_user_id)]
        ),
    )

    result = await service.handle_livzon_feishu_card_callback(
        FakeDb(),
        payload={
            "token": "verify-token",
            "event": {
                "operator": {"open_id": "ou_1"},
                "action": {
                    "value": {
                        "action_id": str(action.id),
                        "action_key": "acknowledge",
                    }
                },
            },
        },
        raw_body=b"{}",
    )

    assert result["toast"]["type"] == "info"
    assert action.clicked_open_id == "ou_old"


@pytest.mark.anyio
async def test_callback_expired_action_is_rejected(monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    action = SimpleNamespace(
        id=uuid.uuid4(),
        card_id="card_1",
        message_id="om_1",
        local_user_id=uuid.uuid4(),
        recipient_open_id="ou_1",
        action_key="start_processing",
        action_label="开始处理",
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        clicked_open_id=None,
        callback_summary=None,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(_callback_config()),
    )
    monkeypatch.setattr(service, "_feishu_card_action_repo", FakeCardActionRepo(action))
    monkeypatch.setattr(
        service,
        "_repo",
        FakeUserRepo(
            [_user(name="点击用户", open_id="ou_1", user_id=action.local_user_id)]
        ),
    )

    result = await service.handle_livzon_feishu_card_callback(
        FakeDb(),
        payload={
            "token": "verify-token",
            "event": {
                "operator": {"open_id": "ou_1"},
                "action": {
                    "value": {
                        "action_id": str(action.id),
                        "action_key": "start_processing",
                    }
                },
            },
        },
        raw_body=b"{}",
    )

    assert action.status == "expired"
    assert result["toast"]["type"] == "warning"


@pytest.mark.anyio
async def test_send_livzon_feishu_message_reports_partial_failure(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.im as im
    import app.platform.integrations.feishu.utils as utils

    ok_user = _user(name="成功用户", open_id="ou_ok")
    failed_user = _user(name="失败用户", open_id="ou_failed")

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_send(**kwargs):
        if kwargs["receive_id"] == "ou_failed":
            return im.FeishuMessageSendResult(
                ok=False,
                code=999,
                error_message="no permission",
            )
        return im.FeishuMessageSendResult(ok=True, message_id="om_ok", code=0)

    monkeypatch.setattr(service, "_feishu_config_repo", FakeFeishuConfigRepo(_config()))
    monkeypatch.setattr(service, "_repo", FakeUserRepo([ok_user, failed_user]))
    monkeypatch.setattr(service, "decrypt_secret", lambda value: "app-secret")
    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(im, "send_feishu_message", fake_send)

    result = await service.send_livzon_feishu_text_message(
        FakeDb(),
        user_ids=[ok_user.id, failed_user.id],
        text="测试消息",
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    assert result["results"][1]["error_code"] == 999
    assert result["results"][1]["error_message"] == "no permission"


@pytest.mark.anyio
async def test_feishu_message_agent_tool_accepts_feishu_recipient_identifier() -> None:
    ensure_agent_tools_registered()
    repo = FakeRepo()
    executor = ToolExecutor(registry=tool_registry, repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="identity.send_feishu_text_message",
            body={"user_ids": ["danhao"], "text": "测试消息"},
            reason="发送测试消息",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"
    assert repo.confirmations[0].request_payload["body"]["user_ids"] == ["danhao"]


@pytest.mark.anyio
async def test_feishu_message_agent_tool_accepts_recipient_aliases() -> None:
    ensure_agent_tools_registered()
    repo = FakeRepo()
    executor = ToolExecutor(registry=tool_registry, repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="identity.send_feishu_message",
            body={"feishu_user_id": "danhao", "message": "偏差记录"},
            reason="发送偏差记录",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"


@pytest.mark.anyio
async def test_feishu_message_agent_tool_accepts_legacy_user_id_content_body() -> None:
    ensure_agent_tools_registered()
    repo = FakeRepo()
    executor = ToolExecutor(registry=tool_registry, repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="identity.send_feishu_message",
            body={
                "user_id": "ou_f062239403858caa9066c43d1dbc2ff7",
                "message_type": "text",
                "content": "偏差记录",
            },
            reason="发送偏差记录",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"


@pytest.mark.anyio
async def test_feishu_message_agent_tool_resolves_feishu_recipient_identifiers(
    monkeypatch,
) -> None:
    user = _user(name="但昊", open_id="ou_f062239403858caa9066c43d1dbc2ff7")
    captured = {}
    repo = FakeRecipientRepo(
        {
            "danhao": [user],
            "ou_f062239403858caa9066c43d1dbc2ff7": [user],
            "112003365": [user],
        }
    )

    async def fake_send(db, *, user_ids, text):
        captured["user_ids"] = user_ids
        captured["text"] = text
        return {"total": 1, "success_count": 1, "failed_count": 0, "results": []}

    monkeypatch.setattr(agent_tools, "UserRepository", lambda: repo)
    monkeypatch.setattr(agent_tools, "send_livzon_feishu_text_message", fake_send)

    result = await agent_tools.send_feishu_text_message(
        SimpleNamespace(db=FakeDb()),
        agent_tools.FeishuTextMessageInput(
            user_ids=[
                "danhao",
                "ou_f062239403858caa9066c43d1dbc2ff7",
                112003365,
            ],
            text="Hi",
        ),
    )

    assert result["success_count"] == 1
    assert captured["user_ids"] == [user.id]
    assert captured["text"] == "Hi"


@pytest.mark.anyio
async def test_feishu_message_agent_tool_reports_unresolved_recipient(
    monkeypatch,
) -> None:
    repo = FakeRecipientRepo({})
    monkeypatch.setattr(agent_tools, "UserRepository", lambda: repo)

    with pytest.raises(HTTPException) as exc_info:
        await agent_tools.send_feishu_text_message(
            SimpleNamespace(db=FakeDb()),
            agent_tools.FeishuTextMessageInput(
                user_ids=["missing-user"],
                text="Hi",
            ),
        )

    assert exc_info.value.status_code == 400
    assert "missing-user" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_feishu_message_agent_tool_requires_confirmation() -> None:
    ensure_agent_tools_registered()
    repo = FakeRepo()
    executor = ToolExecutor(registry=tool_registry, repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="identity.send_feishu_text_message",
            body={"user_ids": [str(uuid.uuid4())], "text": "测试消息"},
            reason="发送测试消息",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"
    assert repo.confirmations[0].operation == "identity.send_feishu_text_message"


@pytest.mark.anyio
async def test_unified_feishu_message_agent_tool_requires_confirmation() -> None:
    ensure_agent_tools_registered()
    repo = FakeRepo()
    executor = ToolExecutor(registry=tool_registry, repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="identity.send_feishu_message",
            body={
                "user_ids": [str(uuid.uuid4())],
                "text": "请处理库存异常",
                "title": "库存异常",
                "value_level": "high",
                "structured": True,
                "requires_business_action": True,
            },
            reason="发送库存异常处理卡片",
        ),
    )

    assert response.ok is True
    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"
    assert repo.confirmations[0].operation == "identity.send_feishu_message"
