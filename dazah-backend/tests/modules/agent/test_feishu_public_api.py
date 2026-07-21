import uuid
from types import SimpleNamespace

import pytest

from app.modules.agent import public_api
from app.platform.identity.models import User


class FakeAgentRepository:
    def __init__(self, session=None) -> None:
        self.session = session
        self.archived: list[dict] = []

    async def get_active_channel_session(self, db, **kwargs):
        return self.session

    async def archive_active_channel_sessions(self, db, **kwargs) -> None:
        self.archived.append(kwargs)


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        name="飞书测试用户",
        feishu_open_id="ou_test",
        status="active",
        is_deleted=False,
    )


@pytest.mark.anyio
async def test_handle_feishu_direct_message_reuses_channel_session(monkeypatch) -> None:
    user = _user()
    existing_session = SimpleNamespace(id=uuid.uuid4())
    repository = FakeAgentRepository(existing_session)
    scope_calls: list[User] = []
    chat_requests = []

    class FakeScopeService:
        async def get_current_scope(self, db, *, user: User) -> None:
            scope_calls.append(user)

    class FakeAgentService:
        def __init__(self, settings) -> None:
            return None

        async def chat(self, db, *, request, current_user):
            chat_requests.append((request, current_user))
            return SimpleNamespace(
                session_id=existing_session.id,
                message=SimpleNamespace(content="已完成查询。"),
                pending_confirmations=[],
            )

    monkeypatch.setattr(public_api, "AgentRepository", lambda: repository)
    monkeypatch.setattr(public_api, "AgentAccessScopeService", FakeScopeService)
    monkeypatch.setattr(public_api, "AgentService", FakeAgentService)
    monkeypatch.setattr(public_api, "get_settings", lambda: SimpleNamespace())

    result = await public_api.handle_feishu_direct_message(
        object(),
        user=user,
        sender_open_id="ou_test",
        message_id="om_test",
        text="查询库存",
    )

    request, request_user = chat_requests[0]
    assert scope_calls == [user]
    assert request_user is user
    assert request.session_id == existing_session.id
    assert request.context["channel"] == "feishu"
    assert request.context["peer_id"] == "ou_test"
    assert result.text == "已完成查询。"


@pytest.mark.anyio
async def test_new_command_archives_only_feishu_channel_session(monkeypatch) -> None:
    user = _user()
    repository = FakeAgentRepository()
    monkeypatch.setattr(public_api, "AgentRepository", lambda: repository)

    result = await public_api.handle_feishu_direct_message(
        object(),
        user=user,
        sender_open_id="ou_test",
        message_id="om_new",
        text="/new",
    )

    assert result.reset is True
    assert repository.archived == [
        {"user_id": user.id, "channel": "feishu", "peer_id": "ou_test"}
    ]
