"""Permission dependency, service, and repository failure-path tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.platform.identity import deps
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.identity.permissions import IdentityPermissionService
from app.platform.identity.schemas import UserModulePermissionsUpdate


def _user(*, role="user", status="active"):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        status=status,
        is_deleted=False,
        grant_version=0,
        updated_at=datetime.now(UTC),
    )


def _request(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_current_user_rejects_missing_invalid_and_disabled_tokens(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(SECRET_KEY="secret")
    session = object()
    assert await deps.get_current_user(
        _request(),
        session,
        settings,
        None,
    ) is None
    assert await deps.get_current_user(
        _request("invalid"),
        session,
        settings,
        None,
    ) is None

    disabled = _user(status="disabled")
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=disabled),
        get_by_feishu_open_id=AsyncMock(),
    )
    monkeypatch.setattr(deps, "UserRepository", lambda: repository)
    token = jwt.encode({"sub": str(disabled.id)}, "secret", algorithm="HS256")
    assert await deps.get_current_user(
        _request(token),
        session,
        settings,
        None,
    ) is None


@pytest.mark.asyncio
async def test_current_user_falls_back_to_cookie_and_open_id(monkeypatch) -> None:
    settings = SimpleNamespace(SECRET_KEY="secret")
    user = _user()
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=None),
        get_by_feishu_open_id=AsyncMock(return_value=user),
    )
    monkeypatch.setattr(deps, "UserRepository", lambda: repository)
    token = jwt.encode(
        {"sub": str(uuid4()), "open_id": "open"},
        "secret",
        algorithm="HS256",
    )
    assert await deps.get_current_user(
        _request(),
        object(),
        settings,
        token,
    ) is user
    repository.get_by_feishu_open_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_required_user_and_admin_matrix() -> None:
    with pytest.raises(HTTPException) as unauthenticated:
        await deps.require_current_user(None)
    assert unauthenticated.value.status_code == 401

    regular = _user()
    with pytest.raises(HTTPException) as forbidden:
        await deps.require_admin(regular)
    assert forbidden.value.status_code == 403
    admin = _user(role="admin")
    assert await deps.require_admin(admin) is admin


@pytest.mark.asyncio
async def test_module_view_supports_all_mode_and_role_grants() -> None:
    dependency = deps.require_module_view("energy")
    regular = _user()
    all_mode = SimpleNamespace(effective_module_access_mode="all")
    assert (
        await dependency(
            current_user=regular,
            db=SimpleNamespace(),
            settings=all_mode,
        )
        is regular
    )

    role_mode = SimpleNamespace(effective_module_access_mode="roles")
    result = SimpleNamespace(scalar_one_or_none=lambda: None)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    with pytest.raises(HTTPException) as missing:
        await dependency(current_user=regular, db=session, settings=role_mode)
    assert missing.value.status_code == 403

    result.scalar_one_or_none = lambda: ["module.agent.read"]
    with pytest.raises(HTTPException) as insufficient:
        await dependency(current_user=regular, db=session, settings=role_mode)
    assert insufficient.value.status_code == 403

    result.scalar_one_or_none = lambda: ["module.view"]
    assert (
        await dependency(current_user=regular, db=session, settings=role_mode)
        is regular
    )
    admin = _user(role="admin")
    assert await dependency(current_user=admin, db=session, settings=role_mode) is admin


@pytest.mark.asyncio
async def test_permission_service_rejects_actor_target_and_version_errors() -> None:
    service = IdentityPermissionService(repo=SimpleNamespace())
    regular = _user()
    with pytest.raises(HTTPException) as actor_error:
        await service.get_user_permissions(
            SimpleNamespace(),
            target_user_id=uuid4(),
            current_user=regular,
        )
    assert actor_error.value.status_code == 403

    admin = _user(role="admin")
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as missing:
        await service.get_user_permissions(
            session,
            target_user_id=uuid4(),
            current_user=admin,
        )
    assert missing.value.status_code == 404

    request = UserModulePermissionsUpdate(
        expected_grant_version=None,
        grants=[],
        reason="test",
    )
    with pytest.raises(HTTPException) as self_change:
        await service.replace_user_permissions(
            SimpleNamespace(),
            target_user_id=admin.id,
            request=request,
            current_user=admin,
        )
    assert self_change.value.status_code == 403

    with pytest.raises(HTTPException) as precondition:
        await service.replace_user_permissions(
            SimpleNamespace(),
            target_user_id=uuid4(),
            request=request,
            current_user=admin,
        )
    assert precondition.value.status_code == 428

    target_id = uuid4()
    repo = SimpleNamespace(get_user_for_update=AsyncMock(return_value=None))
    service = IdentityPermissionService(repo=repo)
    with pytest.raises(HTTPException) as target_missing:
        await service.replace_user_permissions(
            SimpleNamespace(),
            target_user_id=target_id,
            request=request,
            current_user=admin,
            expected_version_from_header=0,
        )
    assert target_missing.value.status_code == 404

    repo.get_user_for_update.return_value = SimpleNamespace(grant_version=2)
    with pytest.raises(HTTPException) as conflict:
        await service.replace_user_permissions(
            SimpleNamespace(),
            target_user_id=target_id,
            request=request,
            current_user=admin,
            expected_version_from_header=1,
        )
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_permission_repository_replaces_revokes_and_creates(
    monkeypatch,
) -> None:
    repository = PermissionGrantRepository()
    actor_id = uuid4()
    user_id = uuid4()
    existing = SimpleNamespace(
        module_code="energy",
        status="active",
        permissions=["module.view"],
        data_scope={"old": True},
        grant_version=1,
        granted_by=actor_id,
        updated_by=None,
    )
    monkeypatch.setattr(
        repository,
        "list_grants",
        AsyncMock(return_value=[existing]),
    )
    added = []
    session = SimpleNamespace(add=added.append, flush=AsyncMock())

    grants = await repository.replace_grants(
        session,
        user_id=user_id,
        grants=[
            {
                "module_code": "warehouse",
                "permissions": ["module.view"],
                "data_scope": {},
            }
        ],
        grant_version=2,
        granted_by=actor_id,
    )
    assert existing.status == "revoked"
    assert existing.permissions == []
    assert grants[0].module_code == "warehouse"
    assert len(added) == 1
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_permission_outbox_state_transitions_truncate_errors() -> None:
    repository = PermissionGrantRepository()
    actor_id = uuid4()
    session = SimpleNamespace(flush=AsyncMock())
    event = SimpleNamespace(
        status="pending",
        processed_at=None,
        last_error="old",
        next_attempt_at=datetime.now(UTC),
        attempts=0,
        updated_by=None,
    )

    await repository.mark_outbox_failed(
        session,
        event,
        error="x" * 3000,
        actor_id=actor_id,
    )
    assert event.status == "failed"
    assert event.attempts == 1
    assert len(event.last_error) == 2000
    assert event.next_attempt_at is not None

    await repository.mark_outbox_processed(
        session,
        event,
        actor_id=actor_id,
    )
    assert event.status == "processed"
    assert event.processed_at is not None
    assert event.last_error is None
    assert event.next_attempt_at is None
    assert event.attempts == 2
