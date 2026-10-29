"""Model-provided confirmation IDs are references, never access grants."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.agent.service import AgentService


@pytest.mark.parametrize(
    "case", ["own", "other_user", "other_session", "deleted", "no_identity"]
)
async def test_model_confirmation_references_cannot_escape_user_and_session(case):
    user_id, session_id = uuid4(), uuid4()
    confirmation = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4() if case == "other_user" else user_id,
        session_id=uuid4() if case == "other_session" else session_id,
        is_deleted=case == "deleted",
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        summary="private confirmation summary",
    )
    service = AgentService(SimpleNamespace())
    service.repo = SimpleNamespace(
        get_session=AsyncMock(
            return_value=None
            if case == "no_identity"
            else SimpleNamespace(user_id=user_id)
        ),
        list_pending_confirmations=AsyncMock(return_value=[]),
        get_confirmation=AsyncMock(return_value=confirmation),
    )
    db = SimpleNamespace()
    result = await service._resolve_pending_confirmations(
        db, {"message": str(confirmation.id)}, session_id=session_id
    )
    assert result == ([confirmation] if case == "own" else [])
    if case == "no_identity":
        service.repo.get_confirmation.assert_not_awaited()
        service.repo.list_pending_confirmations.assert_not_awaited()
    else:
        service.repo.list_pending_confirmations.assert_awaited_once_with(
            db, session_id=session_id, user_id=user_id
        )
