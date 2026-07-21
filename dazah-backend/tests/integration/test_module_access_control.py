import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.agent.access_scope import AgentAccessScopeService
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User, UserModuleGrant
from app.platform.identity.permissions import (
    ADMIN_DEFAULT_MODULE_PERMISSIONS,
    IdentityPermissionService,
)
from app.shared.module_registry import MODULES_BY_CODE


@pytest.mark.anyio
async def test_business_module_routes_require_an_active_view_grant(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Router-level guards must enforce grants outside of Livzon Agent flows."""
    async def override_db():
        yield db_session

    original_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db

    try:
        unauthenticated = await client.get("/api/v1/warehouse/")
        assert unauthenticated.status_code == 401

        user = User(
            name="模块授权测试用户",
            username=f"module-access-{uuid.uuid4().hex[:12]}",
            role="user",
            status="active",
            auth_source="local",
        )
        db_session.add(user)
        await db_session.flush()

        async def override_current_user() -> User:
            return user

        app.dependency_overrides[get_current_user] = override_current_user
        denied = await client.get("/api/v1/warehouse/")
        assert denied.status_code == 403
        assert denied.json()["message"] == "未获授权访问模块：warehouse"

        db_session.add(
            UserModuleGrant(
                user_id=user.id,
                module_code="warehouse",
                permissions=["module.view"],
                data_scope={},
                grant_version=1,
                granted_by=user.id,
                status="active",
            )
        )
        await db_session.flush()

        granted = await client.get("/api/v1/warehouse/")
        assert granted.status_code == 200
        assert granted.json()["code"] == "warehouse"

        other_module = await client.get("/api/v1/production/")
        assert other_module.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override


@pytest.mark.anyio
async def test_current_user_exposes_only_viewable_module_codes(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        name="当前用户模块测试",
        username=f"current-modules-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            UserModuleGrant(
                user_id=user.id,
                module_code="warehouse",
                permissions=["module.view"],
                data_scope={},
                grant_version=1,
                granted_by=user.id,
                status="active",
            ),
            UserModuleGrant(
                user_id=user.id,
                module_code="quality",
                permissions=["module.agent.read"],
                data_scope={},
                grant_version=1,
                granted_by=user.id,
                status="active",
            ),
        ]
    )
    await db_session.flush()

    async def override_db():
        yield db_session

    async def override_current_user() -> User:
        return user

    original_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = await client.get("/api/v1/identity/me")
        assert response.status_code == 200
        assert response.json()["data"]["module_codes"] == ["warehouse"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override


@pytest.mark.anyio
async def test_admin_has_implicit_all_module_and_livzon_access(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = User(
        name="默认全权限管理员",
        username=f"admin-modules-{uuid.uuid4().hex[:12]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(admin)
    await db_session.flush()

    async def override_db():
        yield db_session

    async def override_current_user() -> User:
        return admin

    original_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        me = await client.get("/api/v1/identity/me")
        assert me.status_code == 200
        assert me.json()["data"]["module_codes"] == sorted(MODULES_BY_CODE)

        module_response = await client.get("/api/v1/warehouse/")
        assert module_response.status_code == 200

        scope = await AgentAccessScopeService().scope_out(db_session, user=admin)
        assert {item.module_code for item in scope.modules} == set(MODULES_BY_CODE)
        assert "module.agent.automate" in scope.modules[0].permissions

        permissions = await IdentityPermissionService().get_user_permissions(
            db_session,
            target_user_id=admin.id,
            current_user=admin,
        )
        assert len(permissions.grants) == len(MODULES_BY_CODE)
        assert set(permissions.grants[0].permissions) == set(
            ADMIN_DEFAULT_MODULE_PERMISSIONS
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override
