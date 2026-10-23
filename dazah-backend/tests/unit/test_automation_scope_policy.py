"""Platform automation audit is reserved for system administrators."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.agent.automation_service import AgentAutomationService


def _user(*, role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _automation(
    *, owner_id: uuid.UUID, scope_type: str = "mine", user_ids: list[str] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        owner_user_id=owner_id,
        scope_type=scope_type,
        scope_ref={"user_ids": user_ids or []},
    )


@pytest.mark.asyncio
async def test_ordinary_admin_cannot_query_platform_scope(monkeypatch) -> None:
    service = AgentAutomationService()
    monkeypatch.setattr(
        service.access_scope_service,
        "get_current_scope",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(service, "_is_platform_admin", AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as error:
        await service._effective_query_scope(
            None, user=_user(), scope="platform"
        )
    assert error.value.status_code == 403
    assert (
        await service._effective_query_scope(None, user=_user(), scope="mine")
        == "mine"
    )


def test_platform_scope_only_expands_for_platform_admin() -> None:
    ordinary = _user()
    other = _automation(owner_id=uuid.uuid4())
    shared = _automation(
        owner_id=uuid.uuid4(), scope_type="shared", user_ids=[str(ordinary.id)]
    )
    own = _automation(owner_id=ordinary.id)

    assert (
        AgentAutomationService._can_view(
            ordinary, own, "platform", platform_admin=False
        )
        is True
    )
    assert (
        AgentAutomationService._can_view(
            ordinary, other, "platform", platform_admin=False
        )
        is False
    )
    assert (
        AgentAutomationService._can_view(
            ordinary, shared, "platform", platform_admin=False
        )
        is True
    )
    assert (
        AgentAutomationService._can_view(
            ordinary, other, "platform", platform_admin=True
        )
        is True
    )
