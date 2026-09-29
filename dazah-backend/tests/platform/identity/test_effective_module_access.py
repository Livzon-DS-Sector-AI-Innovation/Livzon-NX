from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.platform.identity import api, deps, rbac, rbac_api
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import (
    PagePermissionService,
    module_codes_from_page_grants,
)
from app.platform.identity.permission_repository import PermissionGrantRepository

PAGE = "hr:employee-management:profile"


@pytest.fixture
def authorization(monkeypatch):
    user = SimpleNamespace(id=uuid4(), name="角色用户", role="user", grant_version=1)
    first = SimpleNamespace(id=uuid4(), name="角色一", code="reader")
    second = SimpleNamespace(id=uuid4(), name="角色二", code="operator")
    roles = [first, second]
    grants = [
        SimpleNamespace(
            role_id=role.id,
            page_key=PAGE,
            permissions=["query"],
            sensitive_actions=[],
            scope_type="department_tree",
            department_ids=[],
        )
        for role in roles
    ]
    overrides = []
    active_keys = {PAGE}
    monkeypatch.setattr(
        rbac, "resolve_user_roles", AsyncMock(side_effect=lambda *a: roles)
    )
    monkeypatch.setattr(
        api, "resolve_user_roles", AsyncMock(side_effect=lambda *a: roles)
    )
    monkeypatch.setattr(api, "resolve_user_permissions", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_page_keys",
        AsyncMock(side_effect=lambda *a: active_keys),
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "list_role_grants",
        AsyncMock(side_effect=lambda *a, **kw: grants),
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "list_user_grants",
        AsyncMock(side_effect=lambda *a, **kw: overrides),
    )
    monkeypatch.setattr(
        PagePermissionRepository, "list_rollouts", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        PagePermissionService, "is_super_admin", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        rbac_api, "_get_target_user_or_404", AsyncMock(return_value=user)
    )
    legacy = AsyncMock(
        side_effect=AssertionError("Legacy module grants are not access facts")
    )
    monkeypatch.setattr(PermissionGrantRepository, "has_module_view", legacy)
    monkeypatch.setattr(PermissionGrantRepository, "list_grants", legacy)
    return user, roles, grants, overrides, active_keys, legacy


@pytest.mark.asyncio
async def test_modules_follow_roles_overrides_and_retired_pages(authorization):
    user, roles, grants, overrides, active_keys, legacy = authorization
    service = PagePermissionService()

    async def modules():
        return module_codes_from_page_grants(
            await service.effective_grants(None, user=user)
        )

    assert await modules() == ["hr"]
    roles.pop()
    assert await modules() == ["hr"]
    overrides.append(
        SimpleNamespace(
            page_key=PAGE,
            permissions=[],
            sensitive_actions=[],
            scope_type="department_tree",
            department_ids=[],
        )
    )
    assert await modules() == []
    overrides.clear()
    assert await modules() == ["hr"]
    roles.clear()
    assert await modules() == []
    overrides.append(
        SimpleNamespace(
            page_key=PAGE,
            permissions=["access"],
            sensitive_actions=[],
            scope_type="department_tree",
            department_ids=[],
        )
    )
    assert await modules() == ["hr"]
    active_keys.clear()
    assert await modules() == []
    legacy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["roles", "all"])
async def test_me_business_api_and_simulator_use_effective_pages(authorization, mode):
    user, roles, grants, overrides, active_keys, legacy = authorization
    application = FastAPI()
    application.include_router(api.user_router, prefix="/api/v1/identity")
    application.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    application.dependency_overrides[deps.get_current_user] = lambda: user
    application.dependency_overrides[rbac_api.require_identity_admin] = lambda: user
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode=mode,
    )

    @application.get(
        "/api/v1/hr/employees", dependencies=[Depends(deps.require_module_view("hr"))]
    )
    async def employees():
        return {"items": []}

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        headers = {"X-Dazah-Page-Key": PAGE}
        response = await client.get("/api/v1/identity/me")
        assert response.status_code == 200
        assert response.json()["data"]["module_codes"] == ["hr"]
        assert (
            await client.get("/api/v1/hr/employees", headers=headers)
        ).status_code == 200
        simulation = await client.post(
            "/api/v1/identity/admin/page-permissions/simulate",
            json={
                "user_id": str(user.id),
                "page_key": PAGE,
                "permission": "query",
            },
        )
        assert simulation.status_code == 200
        assert simulation.json()["data"]["allowed"] is True
        roles.clear()
        assert (await client.get("/api/v1/identity/me")).json()["data"][
            "module_codes"
        ] == []
        assert (
            await client.get("/api/v1/hr/employees", headers=headers)
        ).status_code == 403
        simulation = await client.post(
            "/api/v1/identity/admin/page-permissions/simulate",
            json={
                "user_id": str(user.id),
                "page_key": PAGE,
                "permission": "query",
            },
        )
        assert simulation.status_code == 200
        assert simulation.json()["data"]["allowed"] is False
    legacy.assert_not_awaited()
