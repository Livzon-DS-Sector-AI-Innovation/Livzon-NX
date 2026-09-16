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
            conflict = await client.put(user_url, json=deny)
            assert conflict.status_code == 409
            assert "你基于 v" in conflict.json()["detail"]
            assert "授权管理员" in conflict.json()["detail"]
            restore_key = str(uuid4())
            restored = await client.put(
                user_url,
                json={
                    "expected_grant_version": data["grant_version"],
                    "reason": "恢复角色基线",
                    "grants": [{"page_key": page_key, "mode": "inherit"}],
                    "idempotency_key": restore_key,
                },
            )
            assert restored.status_code == 200, restored.text
            assert restored.json()["data"]["grants"][0]["permissions"] == [
                "access",
                "query",
            ]
            assert restored.json()["data"]["custom_page_keys"] == []
            restored_version = restored.json()["data"]["grant_version"]
            duplicate = await client.put(
                user_url,
                json={
                    "expected_grant_version": data["grant_version"],
                    "reason": "恢复角色基线",
                    "grants": [{"page_key": page_key, "mode": "inherit"}],
                    "idempotency_key": restore_key,
                },
            )
            assert duplicate.status_code == 200, duplicate.text
            assert duplicate.json()["data"]["grant_version"] == restored_version
            reused_key = await client.put(
                user_url,
                json={
                    "expected_grant_version": restored_version,
                    "reason": "另一项调整",
                    "grants": [],
                    "idempotency_key": restore_key,
                },
            )
            assert reused_key.status_code == 409
            assert "幂等键" in reused_key.json()["detail"]

            history_response = await client.get(f"{user_url}/history")
            assert history_response.status_code == 200, history_response.text
            history_page = history_response.json()["data"]
            history = history_page["items"]
            assert history_page["total"] == 2
            assert history_page["page"] == 1
            assert history_page["actor_options"] == [
                {"user_id": str(actor.id), "user_name": "授权管理员"}
            ]
            second_page = await client.get(
                f"{user_url}/history", params={"page": 2, "page_size": 1}
            )
            assert second_page.status_code == 200
            assert second_page.json()["data"]["total"] == 2
            assert second_page.json()["data"]["page"] == 2
            assert len(second_page.json()["data"]["items"]) == 1
            deny_history = next(
                item for item in history if item["reason"] == "明确拒绝此用户页面访问"
            )
            assert deny_history["actor_name"] == "授权管理员"
            assert deny_history["source"] == "manual"
            assert deny_history["changes"][0]["page_key"] == page_key
            filtered = await client.get(
                f"{user_url}/history",
                params={
                    "source": "manual",
                    "page_key": page_key,
                    "change_kind": "grant",
                },
            )
            assert filtered.status_code == 200
            assert filtered.json()["data"]["items"]
            assert filtered.json()["data"]["total"] == 1

            preview = await client.post(
                f"{user_url}/rollback/preview",
                json={
                    "audit_id": deny_history["id"],
                    "expected_grant_version": restored_version,
                },
            )
            assert preview.status_code == 200, preview.text
            preview_data = preview.json()["data"]
            assert preview_data["affected_user_count"] == 1
            assert preview_data["changes"][0]["page_key"] == page_key

            rollback_key = str(uuid4())
            rollback_payload = {
                "audit_id": deny_history["id"],
                "expected_grant_version": restored_version,
                "reason": "恢复拒绝快照",
                "idempotency_key": rollback_key,
            }
            rolled_back = await client.post(
                f"{user_url}/rollback", json=rollback_payload
            )
            assert rolled_back.status_code == 200, rolled_back.text
            rollback_version = rolled_back.json()["data"]["grant_version"]
            duplicate_rollback = await client.post(
                f"{user_url}/rollback", json=rollback_payload
            )
            assert duplicate_rollback.status_code == 200, duplicate_rollback.text
            assert (
                duplicate_rollback.json()["data"]["grant_version"] == rollback_version
            )

            exported = await client.get(f"{user_url}/history/export")
            assert exported.status_code == 200
            assert "授权管理员" in exported.text
            assert "明确拒绝此用户页面访问" in exported.text
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
