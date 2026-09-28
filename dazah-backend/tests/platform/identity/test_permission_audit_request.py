"""Permission audit route regression tests without a database connection."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.agent.access_scope import AgentAccessScopeService
from app.platform.audit import middleware as audit_middleware
from app.platform.audit.middleware import AuditMiddleware, current_audit_request_id
from app.platform.audit.models import AuditLog
from app.platform.identity.api import user_router
from app.platform.identity.deps import require_system_admin
from app.platform.identity.models import User
from app.platform.identity.permissions import IdentityPermissionService
from app.platform.identity.schemas import (
    LivzonAccessScopeOut,
    ModulePermissionGrantOut,
    UserModulePermissionsOut,
    UserModulePermissionsUpdate,
)


class AuditSession:
    def __init__(self) -> None:
        self.records: list[AuditLog] = []

    async def __aenter__(self) -> "AuditSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def add(self, record: AuditLog) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_user", [False, True])
async def test_permission_query_records_snapshot_and_request_correlation(
    monkeypatch: pytest.MonkeyPatch,
    missing_user: bool,
) -> None:
    actor = User(id=uuid4(), name="权限管理员", role="admin")
    target_id = uuid4()
    session = AuditSession()
    result = UserModulePermissionsOut(
        user_id=target_id,
        grant_version=5,
        grants=[
            ModulePermissionGrantOut(
                module_code="quality",
                module_name="质量管理",
                permissions=["module.view"],
                data_scope={"workshop_ids": ["workshop-1"], "api_key": "test-private"},
                grant_version=5,
                granted_by=actor.id,
                status="active",
                updated_at=datetime.now(UTC),
            )
        ],
    )
    query = AsyncMock(
        side_effect=HTTPException(404, "用户不存在") if missing_user else None,
        return_value=result,
    )
    monkeypatch.setattr(IdentityPermissionService, "get_user_permissions", query)
    monkeypatch.setattr(
        AgentAccessScopeService, "get_snapshot", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(audit_middleware, "async_session_factory", lambda: session)
    app = FastAPI()
    app.include_router(user_router, prefix="/api/v1/identity")
    app.add_middleware(AuditMiddleware)

    async def override_admin(request: Request) -> User:
        request.state.audit_user_id = actor.id
        return actor

    async def override_db() -> Any:
        return session

    app.dependency_overrides[require_system_admin] = override_admin
    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/identity/users/{target_id}/module-permissions"
        )

    assert response.status_code == (404 if missing_user else 200)
    if missing_user:
        assert response.json()["detail"] == "用户不存在"
        assert len(session.records) == 1
        assert session.records[0].status_code == 404
        return
    data = response.json()["data"]
    assert data == result.model_dump(mode="json")
    assert len(session.records) == 2
    event, operation = session.records
    assert event.action == "view_user_module_permissions"
    assert event.resource_id == target_id
    assert event.request_id == operation.request_id == response.headers["X-Request-ID"]
    assert event.new_value is not None
    assert event.new_value["grants"][0]["permissions"] == ["module.view"]
    assert event.new_value["grants"][0]["data_scope"] == {
        "workshop_ids": ["workshop-1"],
        "api_key": "***",
    }
    assert "test-private" not in str(event.new_value)
    assert event.old_value is None
    assert event.extra == {"grant_version": 5}


@pytest.mark.asyncio
async def test_permission_write_and_history_keep_request_correlation() -> None:
    actor = User(id=uuid4(), role="admin")
    target = User(id=uuid4(), grant_version=5)
    repo = SimpleNamespace(
        get_user_for_update=AsyncMock(return_value=target),
        list_grants=AsyncMock(return_value=[]),
        replace_grants=AsyncMock(return_value=[]),
        create_outbox_event=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    records: list[AuditLog] = []
    db = SimpleNamespace(
        add=records.append,
        flush=AsyncMock(),
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [])
            )
        ),
    )
    token = current_audit_request_id.set("permission-write-request")
    try:
        await IdentityPermissionService(repo).replace_user_permissions(
            db,
            target_user_id=target.id,
            current_user=actor,
            request=UserModulePermissionsUpdate(
                expected_grant_version=5, grants=[], reason="撤销模块授权"
            ),
        )
        await IdentityPermissionService(repo).list_permission_audit(
            db,
            target_user_id=target.id,
            current_user=actor,
            limit=20,
        )
    finally:
        current_audit_request_id.reset(token)
    assert [record.action for record in records] == [
        "replace_user_module_permissions",
        "view_user_permission_audit",
    ]
    assert all(record.request_id == "permission-write-request" for record in records)
    assert records[0].old_value == {"grants": []}
    assert records[0].new_value == {"grants": []}
    assert records[0].extra["grant_version"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [False, True])
async def test_livzon_scope_audit_correlates_requests(
    monkeypatch: pytest.MonkeyPatch,
    sync: bool,
) -> None:
    actor = User(id=uuid4(), role="admin")
    target_id = uuid4()
    session = AuditSession()
    scope = LivzonAccessScopeOut(
        user_id=target_id,
        source_grant_version=5,
        agent_scope_version=6,
        registry_version="registry-1",
        sync_status="synced",
        tool_names=["quality.list_deviations"],
    )
    monkeypatch.setattr(
        IdentityPermissionService,
        "get_user_permissions",
        AsyncMock(
            return_value=UserModulePermissionsOut(user_id=target_id, grant_version=5)
        ),
    )
    monkeypatch.setattr(
        AgentAccessScopeService, "get_snapshot", AsyncMock(return_value=scope)
    )
    monkeypatch.setattr(
        AgentAccessScopeService, "synchronize", AsyncMock(return_value=scope)
    )
    monkeypatch.setattr(
        AgentAccessScopeService, "snapshot_out", staticmethod(lambda _snapshot: scope)
    )
    monkeypatch.setattr(audit_middleware, "async_session_factory", lambda: session)
    app = FastAPI()
    app.include_router(user_router, prefix="/api/v1/identity")
    app.add_middleware(AuditMiddleware)

    async def override_admin(request: Request) -> User:
        request.state.audit_user_id = actor.id
        return actor

    async def override_db() -> Any:
        return session

    app.dependency_overrides[require_system_admin] = override_admin
    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/api/v1/identity/users/{target_id}/livzon-access-scope"
        response = await client.request(
            "POST" if sync else "GET", path + ("/sync" if sync else "")
        )
    assert response.status_code == 200
    assert response.json()["data"] == scope.model_dump(mode="json")
    event, operation = session.records
    assert event.request_id == operation.request_id == response.headers["X-Request-ID"]
    assert event.action == (
        "sync_user_livzon_access_scope" if sync else "view_user_livzon_access_scope"
    )
    assert event.new_value == (
        {"source_grant_version": 5, "agent_scope_version": 6, "sync_status": "synced"}
        if sync
        else scope.model_dump(mode="json")
    )
