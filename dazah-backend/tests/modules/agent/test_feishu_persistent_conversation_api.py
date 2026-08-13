import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.agent import api
from app.modules.agent.service import AgentService
from app.platform.identity.models import User


@pytest.mark.anyio
async def test_feishu_conversation_route_persists_history_and_is_idempotent(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        name="飞书持久会话用户",
        username=f"feishu-session-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="feishu",
        tenant_key="tenant-a",
    )
    db_session.add(user)
    await db_session.flush()

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def allow_scope(self, db, *, user):
        return None

    monkeypatch.setattr(api, "require_service_token", lambda *args: None)
    monkeypatch.setattr(
        api.AgentAccessScopeService,
        "get_current_scope",
        allow_scope,
    )
    app.dependency_overrides[get_db] = override_db
    trace_id = uuid.uuid4()
    run_id = uuid.uuid4()
    message_id = f"om_{uuid.uuid4().hex}"
    prepare_payload = {
        "subject": {
            "tenant_id": "tenant-a",
            "user_id": str(user.id),
            "source": "feishu",
        },
        "peer_id": "feishu:oc_group:on_user",
        "external_message_id": message_id,
        "message": "查询未关闭偏差",
        "trace_id": str(trace_id),
        "run_id": str(run_id),
        "source": {
            "platform": "feishu",
            "sender_open_id": "ou_test",
            "chat_id": "oc_group",
            "chat_type": "group",
            "message_id": message_id,
        },
        "attachments": [],
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            prepared = await client.post(
                "/api/v1/agent/internal/feishu/conversations/prepare",
                headers={"Authorization": "Bearer internal-test"},
                json=prepare_payload,
            )
            assert prepared.status_code == 200
            prepared_data = prepared.json()
            assert prepared_data["duplicate"] is False
            assert prepared_data["messages"] == []
            session_id = prepared_data["session_id"]

            completed = await client.post(
                f"/api/v1/agent/internal/feishu/conversations/{session_id}/complete",
                headers={"Authorization": "Bearer internal-test"},
                json={
                    "subject": prepare_payload["subject"],
                    "external_message_id": message_id,
                    "trace_id": str(trace_id),
                    "run_id": str(run_id),
                    "assistant_message": "发现 2 条未关闭偏差",
                    "tool_trace": [
                        {
                            "operation": "quality.list_deviations",
                            "status": "completed",
                            "ok": True,
                            "secret": "must-not-be-persisted",
                        }
                    ],
                },
            )
            assert completed.status_code == 200
            assert completed.json()["duplicate"] is False

            replay = await client.post(
                "/api/v1/agent/internal/feishu/conversations/prepare",
                headers={"Authorization": "Bearer internal-test"},
                json=prepare_payload,
            )
            assert replay.status_code == 200
            assert replay.json()["duplicate"] is True
            assert replay.json()["response_text"] == "发现 2 条未关闭偏差"

            reset_payload = {
                **prepare_payload,
                "external_message_id": f"om_{uuid.uuid4().hex}",
                "message": "/restart",
                "trace_id": str(uuid.uuid4()),
                "run_id": str(uuid.uuid4()),
            }
            reset_payload["source"] = {
                **prepare_payload["source"],
                "message_id": reset_payload["external_message_id"],
            }
            reset = await client.post(
                "/api/v1/agent/internal/feishu/conversations/prepare",
                headers={"Authorization": "Bearer internal-test"},
                json=reset_payload,
            )
            assert reset.status_code == 200
            assert reset.json()["session_id"] != session_id
            assert reset.json()["messages"] == []

        detail = await AgentService(settings=object()).get_session_detail(
            db_session,
            session_id=uuid.UUID(session_id),
            current_user=user,
        )
        assert detail.session.channel == "feishu"
        assert detail.session.status == "archived"
        assert [item.content for item in detail.messages] == [
            "查询未关闭偏差",
            "发现 2 条未关闭偏差",
        ]
        assert detail.messages[1].metadata["trace_id"] == str(trace_id)
        assert "secret" not in str(detail.messages[1].metadata)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_feishu_conversation_route_rejects_cross_tenant_subject(
    db_session: AsyncSession,
) -> None:
    user = User(
        name="跨租户测试用户",
        username=f"feishu-tenant-{uuid.uuid4().hex[:12]}",
        status="active",
        tenant_key="tenant-a",
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await api._require_feishu_subject_user(
            db_session,
            subject=api.AgentTrustedSubject(
                tenant_id="tenant-b",
                user_id=user.id,
                source="feishu",
            ),
        )
    assert getattr(exc.value, "status_code", None) == 403
