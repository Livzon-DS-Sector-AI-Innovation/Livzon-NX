from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.audit.models import AuditLog
from app.platform.identity import deps, rbac_api
from app.platform.identity.models import (
    Menu,
    PermissionOutboxEvent,
    Role,
    User,
    UserRole,
)


@pytest.mark.asyncio
async def test_versioned_role_and_user_replacement_keeps_baseline_audit_and_outbox(
    db_session,
    monkeypatch,
):
    # Endpoint commits release only savepoints; fixture rollback owns test data.
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(name="授权管理员", role="admin")
        user = User(name="页面经办员", role="user")
        role = Role(name="页面只读角色", code=f"page_test_{uuid4().hex}")
        db.add_all([actor, user, role])
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id, source="manual"))
        page_key = "hr:recruitment"
        menu = await db.scalar(select(Menu).where(Menu.key == page_key))
        if menu is None:
            menu = Menu(key=page_key, name="招聘管理", type="menu")
            db.add(menu)
        menu.status = "active"
        menu.type = "menu"
        menu.is_deleted = False
        menu.parent_id = None
        menu.route_path = "/hr/recruitment"
        await db.flush()

        app = FastAPI()
        app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[deps.get_current_user] = lambda: actor
        monkeypatch.setattr(rbac_api, "publish_permissions_changed", AsyncMock())
        monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", AsyncMock())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            role_url = f"/api/v1/identity/admin/roles/{role.id}/page-permissions"
            user_url = f"/api/v1/identity/admin/users/{user.id}/page-permissions"
            response = await client.put(
                role_url,
                json={
                    "expected_grant_version": role.grant_version,
                    "reason": "建立页面只读基线",
                    "grants": [
                        {
                            "page_key": page_key,
                            "permissions": ["query"],
                            "data_scope": {"scope_type": "department_tree"},
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["data"]["grants"][0]["permissions"] == [
                "access",
                "query",
            ]
            current = (await client.get(user_url)).json()["data"]
            version = current["grant_version"]
            deny = {
                "expected_grant_version": version,
                "reason": "明确拒绝此用户页面访问",
                "grants": [
                    {
                        "page_key": page_key,
                        "permissions": [],
                        "data_scope": {"scope_type": "department_tree"},
                    }
                ],
            }
            response = await client.put(user_url, json=deny)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["grants"][0]["permissions"] == []
            assert data["role_grants"][0]["permissions"] == ["access", "query"]
            assert data["custom_page_keys"] == [page_key]
            assert (await client.put(user_url, json=deny)).status_code == 409
            restored = await client.put(
                user_url,
                json={
                    "expected_grant_version": data["grant_version"],
                    "reason": "恢复角色基线",
                    "grants": [{"page_key": page_key, "mode": "inherit"}],
                },
            )
            assert restored.status_code == 200, restored.text
            assert restored.json()["data"]["grants"][0]["permissions"] == [
                "access",
                "query",
            ]
            assert restored.json()["data"]["custom_page_keys"] == []
            logs = (
                await db.scalars(
                    select(AuditLog).where(
                        AuditLog.resource_id == user.id,
                        AuditLog.action == "replace_user_page_permissions",
                    )
                )
            ).all()
            assert len(logs) == 2
            assert logs[0].new_value["reason"] == "明确拒绝此用户页面访问"
            events = (
                await db.scalars(
                    select(PermissionOutboxEvent).where(
                        PermissionOutboxEvent.user_id == user.id
                    )
                )
            ).all()
            assert {event.grant_version for event in events} >= {
                version + 1,
                version + 2,
            }

            app.dependency_overrides[deps.get_current_user] = lambda: user
            assert (await client.get(user_url)).status_code == 403
            app.dependency_overrides[deps.get_current_user] = lambda: None
            assert (await client.get(user_url)).status_code == 401
