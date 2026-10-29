"""Delegation tokens are purpose-bound and expire independently of service keys."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.platform.identity import agent_delegation as delegation
from app.platform.identity.models import User


@pytest.mark.parametrize("invalid", ["expired", "audience", "session_jwt"])
async def test_delegation_rejects_expiry_and_other_token_purposes(invalid):
    user = User(id=uuid4(), name="audit", tenant_key="factory", session_version=1)
    settings = SimpleNamespace(SECRET_KEY="x" * 40)
    token = delegation.issue_agent_delegation(settings, user, source="web")
    claims = jwt.decode(token, options={"verify_signature": False})
    if invalid == "expired":
        claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    if invalid == "audience":
        claims["aud"] = "another-service"
    token = jwt.encode(
        claims,
        settings.SECRET_KEY
        if invalid == "session_jwt"
        else delegation._signing_key(settings),
        algorithm="HS256",
    )
    db = SimpleNamespace(get=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await delegation.require_agent_delegation(
            db, settings, token, user_id=user.id, tenant_id="factory", source="web"
        )
    assert error.value.status_code == 401
    db.get.assert_not_awaited()


@pytest.mark.parametrize("state", ["active", "suspended", "deleted"])
async def test_feishu_delegation_rechecks_its_signed_external_binding(state):
    user = User(
        id=uuid4(),
        name="audit",
        tenant_key="factory",
        session_version=1,
        status="active",
        is_deleted=False,
    )
    binding = SimpleNamespace(
        id=uuid4(), local_user_id=user.id, status=state, is_deleted=state == "deleted"
    )
    settings = SimpleNamespace(SECRET_KEY="x" * 40)
    token = delegation.issue_agent_delegation(
        settings, user, source="feishu", external_binding_id=binding.id
    )
    db = SimpleNamespace(get=AsyncMock(side_effect=[user, binding]))
    if state == "active":
        result = await delegation.require_agent_delegation(
            db,
            settings,
            token,
            user_id=user.id,
            tenant_id="factory",
            source="feishu",
            external_binding_id=binding.id,
        )
        assert result is user
    else:
        with pytest.raises(HTTPException) as error:
            await delegation.require_agent_delegation(
                db,
                settings,
                token,
                user_id=user.id,
                tenant_id="factory",
                source="feishu",
                external_binding_id=binding.id,
            )
        assert error.value.status_code == 403


async def test_external_binding_id_cannot_be_replaced_in_request():
    user = User(id=uuid4(), name="audit", tenant_key="factory", session_version=1)
    settings = SimpleNamespace(SECRET_KEY="x" * 40)
    token = delegation.issue_agent_delegation(
        settings, user, source="feishu", external_binding_id=uuid4()
    )
    db = SimpleNamespace(get=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await delegation.require_agent_delegation(
            db,
            settings,
            token,
            user_id=user.id,
            tenant_id="factory",
            source="feishu",
            external_binding_id=uuid4(),
        )
    assert error.value.status_code == 401
    db.get.assert_not_awaited()
