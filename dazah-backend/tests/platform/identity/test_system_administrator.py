"""Unified identity, revocation and last-administrator regression coverage."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity import api, deps, rbac_api
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    resolve_user_department_scope,
)
from app.platform.identity.models import Role, User, UserRole
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.rbac import resolve_user_permissions


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["hr", "warehouse", "quality", "procurement"])
async def test_admin_can_use_business_routes_without_page_grants(module):
    user = User(id=uuid4(), name="系统管理员", role="admin")
    app = FastAPI()
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None

    @app.get("/business", dependencies=[Depends(deps.require_module_view(module))])
    async def business():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/business")).status_code == 200
        app.dependency_overrides[deps.get_current_user] = lambda: None
        assert (await client.get("/business")).status_code == 401


@pytest.mark.asyncio
async def test_admin_ignores_old_scopes_and_page_scope_cache():
    token = current_page_data_scope.set(
        {"scope_type": "departments", "department_ids": []}
    )
    try:
        scope = await resolve_user_department_scope(None, User(role="admin"))
        assert scope.is_all
    finally:
        current_page_data_scope.reset(token)


@pytest.mark.asyncio
async def test_admin_keeps_business_context_for_registered_routes():
    user = User(id=uuid4(), name="系统管理员", role="admin")
    app = FastAPI()
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None

    @app.get(
        "/api/v1/hr/employees", dependencies=[Depends(deps.require_module_view("hr"))]
    )
    async def employees():
        return {
            "actor": str(current_page_actor.get().id),
            "scope": current_page_data_scope.get(),
        }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/hr/employees")
        assert response.status_code == 200
        assert response.json() == {
            "actor": str(user.id),
            "scope": {"scope_type": "all", "department_ids": []},
        }
        assert (
            await client.get(
                "/api/v1/hr/employees", headers={"X-Dazah-Page-Key": "hr:recruitment"}
            )
        ).status_code == 403


@pytest.mark.asyncio
async def test_role_and_identity_promotion_demotion_are_consistent(
    db_session, monkeypatch
):
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(
            name=f"系统管理员-{uuid4().hex}",
            username=f"system-admin-{uuid4().hex}",
            role="admin",
        )
        target = User(name="身份合并测试", role="user")
        role = await db.scalar(select(Role).where(Role.code == "super_admin"))
        if role is None:
            role = Role(name="系统管理员", code="super_admin", is_system=True)
            db.add(role)
        db.add_all([actor, target])
        await db.flush()
        app = FastAPI()
        app.include_router(api.user_router, prefix="/identity")
        app.include_router(rbac_api.rbac_router, prefix="/identity")
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[deps.get_current_user] = lambda: actor
        for module in (api, rbac_api):
            monkeypatch.setattr(module, "publish_permissions_changed", AsyncMock())
            monkeypatch.setattr(module, "publish_data_scope_changed", AsyncMock())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            roles_url = f"/identity/admin/users/{target.id}/roles"
            user_url = f"/identity/users/{target.id}"
            assert await resolve_user_permissions(db, actor.id) == ["*"]
            listed = await client.get(
                "/identity/admin/users", params={"keyword": actor.name}
            )
            actor_item = next(
                item
                for item in listed.json()["data"]["items"]
                if item["id"] == str(actor.id)
            )
            assert any(item["name"] == "系统管理员" for item in actor_item["roles"])
            response = await client.post(roles_url, json={"role_ids": [str(role.id)]})
            assert response.status_code == 200, response.text
            assert target.role == "admin"
            assert await PagePermissionService().is_super_admin(db, user_id=target.id)
            assert await resolve_user_permissions(db, target.id) == ["*"]
            promoted_version = target.grant_version

            response = await client.put(user_url, json={"role": "user"})
            assert response.status_code == 200, response.text
            assert target.grant_version > promoted_version
            assert not await PagePermissionService().is_super_admin(
                db, user_id=target.id
            )
            assert "*" not in await resolve_user_permissions(db, target.id)
            assert not await db.scalar(
                select(UserRole).where(
                    UserRole.user_id == target.id,
                    UserRole.role_id == role.id,
                    UserRole.is_deleted.is_(False),
                )
            )
            assert (
                await client.put(user_url, json={"role": "admin"})
            ).status_code == 200
            assert (
                await client.put(
                    f"/identity/admin/users/{target.id}/page-permissions",
                    json={
                        "expected_grant_version": target.grant_version,
                        "grants": [],
                        "reason": "不能限制管理员",
                    },
                )
            ).status_code == 400

            # Force the last-admin result to exercise both identity entry points.
            monkeypatch.setattr(
                api, "active_system_admin_count", AsyncMock(return_value=1)
            )
            monkeypatch.setattr(
                rbac_api, "_active_super_admin_count", AsyncMock(return_value=1)
            )
            assert (
                await client.put(user_url, json={"status": "disabled"})
            ).status_code == 409
            assert (
                await client.put(user_url, json={"role": "user"})
            ).status_code == 409
            assert (await client.delete(f"{roles_url}/{role.id}")).status_code == 409
            monkeypatch.setattr(
                rbac_api, "_active_super_admin_count", AsyncMock(return_value=2)
            )
            assert (await client.delete(f"{roles_url}/{role.id}")).status_code == 200
            assert target.role == "user"
            assert (
                await client.put(f"/identity/users/{actor.id}", json={"role": "user"})
            ).status_code == 403
