"""Rollback endpoints preserve versions, audit history and cache invalidation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.platform.identity import rbac_api


def _result() -> SimpleNamespace:
    return SimpleNamespace(model_dump=lambda **_kwargs: {"saved": True})


@pytest.mark.asyncio
async def test_conflict_names_the_latest_actor_and_reason(monkeypatch) -> None:
    history = SimpleNamespace(
        actor_name="审核员", reason="范围变更",
        created_at=datetime(2026, 9, 16, 8, 0, tzinfo=UTC),
    )
    service = SimpleNamespace(permission_history=AsyncMock(return_value=[history]))
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)

    with pytest.raises(HTTPException) as error:
        await rbac_api._raise_page_grant_conflict(
            object(), resource_type="identity.user_page_permissions",
            resource_id=uuid4(), submitted_version=2, current_version=3,
        )
    assert error.value.status_code == 409
    assert "审核员" in error.value.detail
    assert "范围变更" in error.value.detail


@pytest.mark.asyncio
async def test_user_rollback_replays_snapshot_with_a_new_version(monkeypatch) -> None:
    actor = SimpleNamespace(id=uuid4(), role="admin")
    user = SimpleNamespace(
        id=uuid4(), name="目标用户", role="user", grant_version=3, updated_by=None
    )
    history = SimpleNamespace(id=uuid4(), new_value={"grants": [], "grant_version": 2})
    permission_repo = SimpleNamespace(
        get_user_for_update=AsyncMock(return_value=user),
        create_outbox_event=AsyncMock(),
    )
    page_repo = SimpleNamespace(
        get_page_permission_history=AsyncMock(return_value=history),
        list_user_grants=AsyncMock(return_value=[]),
        replace_user_grants=AsyncMock(return_value=[]),
    )
    service = SimpleNamespace(
        normalize_inputs=Mock(return_value=[]),
        validate_department_ids=AsyncMock(),
        user_permissions_out=AsyncMock(return_value=_result()),
    )
    audit = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "PermissionGrantRepository", lambda: permission_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: page_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "publish_permissions_changed", publish)
    db = SimpleNamespace(commit=AsyncMock())
    body = SimpleNamespace(
        audit_id=history.id, expected_grant_version=3,
        reason="恢复受控授权", idempotency_key=None,
    )

    response = await rbac_api.rollback_user_page_permissions(user.id, body, actor, db)
    assert response.status_code == 200
    assert user.grant_version == 4
    assert user.updated_by == actor.id
    permission_repo.create_outbox_event.assert_awaited_once_with(
        db, user_id=user.id, grant_version=4, actor_id=actor.id,
        event_type="identity.user_page_grants.changed.v1",
    )
    assert audit.await_args.kwargs["new_value"]["rollback_of"] == str(history.id)
    db.commit.assert_awaited_once()
    publish.assert_awaited_once_with(user.id)


@pytest.mark.asyncio
async def test_role_rollback_replays_snapshot_and_invalidates_users(
    monkeypatch,
) -> None:
    actor = SimpleNamespace(id=uuid4(), role="admin")
    role = SimpleNamespace(
        id=uuid4(), name="质检角色", code="quality", grant_version=5, updated_by=None
    )
    history = SimpleNamespace(id=uuid4(), new_value={"grants": [], "grant_version": 4})
    page_repo = SimpleNamespace(
        get_role_for_update=AsyncMock(return_value=role),
        get_page_permission_history=AsyncMock(return_value=history),
        list_role_grants=AsyncMock(return_value=[]),
        replace_role_grants=AsyncMock(return_value=[]),
    )
    service = SimpleNamespace(
        normalize_inputs=Mock(return_value=[]),
        validate_department_ids=AsyncMock(),
        role_permissions_out=AsyncMock(return_value=_result()),
    )
    audit = AsyncMock()
    bump = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: page_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(rbac_api, "resolve_user_roles", AsyncMock(return_value=[]))
    monkeypatch.setattr(rbac_api, "_bump_all_user_grant_versions", bump)
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", publish)
    db = SimpleNamespace(commit=AsyncMock())
    body = SimpleNamespace(
        audit_id=history.id, expected_grant_version=5,
        reason="恢复角色基线", idempotency_key=None,
    )

    response = await rbac_api.rollback_role_page_permissions(role.id, body, actor, db)
    assert response.status_code == 200
    assert role.grant_version == 6
    assert role.updated_by == actor.id
    assert audit.await_args.kwargs["new_value"]["rollback_of"] == str(history.id)
    bump.assert_awaited_once_with(db, actor_id=actor.id)
    db.commit.assert_awaited_once()
    publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_rollback_preview_reports_expansion_without_writing(
    monkeypatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), name="目标用户", grant_version=3)
    history = SimpleNamespace(new_value={"grants": [], "grant_version": 2})
    page_repo = SimpleNamespace(
        get_page_permission_history=AsyncMock(return_value=history),
        list_user_grants=AsyncMock(return_value=[]),
    )
    service = SimpleNamespace(
        normalize_inputs=Mock(return_value=[]),
        validate_department_ids=AsyncMock(),
        history_changes=Mock(return_value=[SimpleNamespace(kind="grant")]),
    )
    captured: dict[str, object] = {}

    def preview_result(**fields):
        captured.update(fields)
        return SimpleNamespace(model_dump=lambda **_kwargs: {"target_type": "user"})

    monkeypatch.setattr(
        rbac_api, "_get_target_user_or_404", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: page_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(rbac_api, "PagePermissionRollbackPreviewOut", preview_result)
    monkeypatch.setattr(
        rbac_api, "RolePagePermissionAffectedUserOut", lambda **fields: fields
    )
    body = SimpleNamespace(audit_id=uuid4(), expected_grant_version=3)

    response = await rbac_api.preview_user_page_permission_rollback(
        user.id, body, SimpleNamespace(id=uuid4()), object()
    )
    assert response.status_code == 200
    assert captured["expanded_user_count"] == 1
    assert captured["restricted_user_count"] == 0
    assert captured["history_grant_version"] == 2
    assert captured["affected_user_samples"][0]["user_id"] == user.id
    service.validate_department_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_role_rollback_preview_uses_affected_user_analysis(monkeypatch) -> None:
    role = SimpleNamespace(id=uuid4(), name="质检角色", grant_version=5)
    history = SimpleNamespace(new_value={"grants": [], "grant_version": 4})
    page_repo = SimpleNamespace(
        get_page_permission_history=AsyncMock(return_value=history),
        list_role_grants=AsyncMock(return_value=[]),
    )
    impact = SimpleNamespace(
        affected_user_count=3, expanded_user_count=0,
        restricted_user_count=2, mixed_user_count=1,
        users_with_overrides=1, affected_user_samples=[],
    )
    service = SimpleNamespace(
        normalize_inputs=Mock(return_value=[]),
        validate_department_ids=AsyncMock(),
        role_permissions_preview=AsyncMock(return_value=impact),
        history_changes=Mock(return_value=[]),
    )
    captured: dict[str, object] = {}

    def preview_result(**fields):
        captured.update(fields)
        return SimpleNamespace(model_dump=lambda **_kwargs: {"target_type": "role"})

    monkeypatch.setattr(rbac_api, "_get_role_or_404", AsyncMock(return_value=role))
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: page_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(rbac_api, "PagePermissionRollbackPreviewOut", preview_result)
    body = SimpleNamespace(audit_id=uuid4(), expected_grant_version=5)
    settings = SimpleNamespace(effective_module_access_mode="saved")

    response = await rbac_api.preview_role_page_permission_rollback(
        role.id, body, SimpleNamespace(id=uuid4()), object(), settings
    )
    assert response.status_code == 200
    assert captured["affected_user_count"] == 3
    assert captured["restricted_user_count"] == 2
    assert captured["history_grant_version"] == 4
    assert service.role_permissions_preview.await_args.kwargs[
        "module_access_mode"
    ] == "saved"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type", ["user", "role"])
async def test_rollback_retry_returns_existing_result_without_new_write(
    monkeypatch, target_type: str
) -> None:
    actor = SimpleNamespace(id=uuid4(), role="admin")
    target = SimpleNamespace(
        id=uuid4(), role="user" if target_type == "user" else None,
        code="quality", grant_version=7,
    )
    audit_id = uuid4()
    key = uuid4()
    reason = "重复提交仍只恢复一次"
    existing = SimpleNamespace(new_value={
        "request_fingerprint": rbac_api._page_permission_request_fingerprint(
            reason=reason, audit_id=audit_id
        )
    })
    page_repo = SimpleNamespace(
        get_role_for_update=AsyncMock(return_value=target),
        find_page_permission_idempotency=AsyncMock(return_value=existing),
    )
    permission_repo = SimpleNamespace(
        get_user_for_update=AsyncMock(return_value=target)
    )
    service = SimpleNamespace(
        role_permissions_out=AsyncMock(return_value=_result()),
        user_permissions_out=AsyncMock(return_value=_result()),
    )
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: page_repo)
    monkeypatch.setattr(rbac_api, "PermissionGrantRepository", lambda: permission_repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(rbac_api, "resolve_user_roles", AsyncMock(return_value=[]))
    db = SimpleNamespace(commit=AsyncMock())
    body = SimpleNamespace(
        audit_id=audit_id, expected_grant_version=5,
        reason=reason, idempotency_key=key,
    )

    if target_type == "user":
        response = await rbac_api.rollback_user_page_permissions(
            target.id, body, actor, db
        )
        service.user_permissions_out.assert_awaited_once()
    else:
        response = await rbac_api.rollback_role_page_permissions(
            target.id, body, actor, db
        )
        service.role_permissions_out.assert_awaited_once()

    assert response.status_code == 200
    assert target.grant_version == 7
    assert page_repo.find_page_permission_idempotency.await_args.kwargs[
        "idempotency_key"
    ] == key
    db.commit.assert_not_awaited()
