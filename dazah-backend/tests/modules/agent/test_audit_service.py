import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.modules.agent.audit_service import (
    AgentAuditService,
    _session_channel_filter,
    redact_audit_value,
)
from app.modules.agent.models import AgentSession
from app.platform.identity.models import User


def test_redact_audit_value_removes_nested_credentials() -> None:
    payload = {
        "query": "设备状态",
        "authorization": "Bearer secret",
        "nested": {
            "api_key": "sk-test",
            "items": [{"password": "unsafe", "value": 42}],
        },
    }

    assert redact_audit_value(payload) == {
        "query": "设备状态",
        "authorization": "[REDACTED]",
        "nested": {
            "api_key": "[REDACTED]",
            "items": [{"password": "[REDACTED]", "value": 42}],
        },
    }


def test_audit_session_without_channel_defaults_to_web() -> None:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    session = AgentSession(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Web 会话",
        status="active",
        context={"entry": "floating-assistant"},
        created_at=now,
        updated_at=now,
    )
    user = User(
        id=user_id,
        username="audit-user",
        name="审计用户",
        password_hash="unused",
        role="user",
        status="active",
        auth_source="local",
        created_at=now,
        updated_at=now,
    )

    item = AgentAuditService._session_item(session, user, 1, 0, 0)

    assert item.channel == "web"


def test_web_channel_filter_coalesces_missing_context_to_web() -> None:
    statement = select(AgentSession.id).where(_session_channel_filter("web"))
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "coalesce" in compiled
    assert "'web'" in compiled
