"""Built-in roles remain manageable except for the system administrator."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import deps, rbac_api
from app.platform.identity.models import Role, User


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["edit", "delete", "menus"])
@pytest.mark.parametrize(
    ("code", "is_system", "expected_status"),
    [
        ("material_qa", True, 200),
        ("custom", False, 200),
        ("super_admin", True, 400),
        ("super_admin", False, 400),
    ],
)
async def test_role_operations(
    monkeypatch, operation, code, is_system, expected_status
):
    role = Role(
        id=uuid4(), name="角色", code=code, is_system=is_system, grant_version=0
    )
    db = AsyncMock()
    actor = User(id=uuid4(), role="admin", status="active", is_deleted=False)
    monkeypatch.setattr(
        rbac_api, "lock_authorization_actor", AsyncMock(return_value=actor)
    )
    monkeypatch.setattr(
        rbac_api.RbacRepository, "get_role_by_id", AsyncMock(return_value=role)
    )
    monkeypatch.setattr(
        rbac_api.RbacRepository,
        "list_role_permission_codes",
        AsyncMock(return_value=[]),
    )
    menu_write = AsyncMock()
    monkeypatch.setattr(rbac_api.MenuRepository, "set_role_menus", menu_write)
    audit = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "_bump_all_user_grant_versions", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", publish)
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/identity")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/identity/admin/roles/{role.id}"
        if operation == "edit":
            response = await client.put(
                url, json={"name": "已修改", "description": "新说明"}
            )
        elif operation == "delete":
            response = await client.delete(url)
        else:
            response = await client.put(f"{url}/menus", json={"menu_ids": []})
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        db.commit.assert_awaited_once()
        audit.assert_awaited_once()
        publish.assert_awaited_once()
        data = response.json()["data"]
        if operation == "edit":
            assert data["name"] == role.name == "已修改"
            assert data["description"] == "新说明"
            assert data["is_system"] is is_system
        elif operation == "delete":
            assert role.is_deleted is True
            assert data["message"] == "角色已删除"
        else:
            menu_write.assert_awaited_once_with(db, role.id, [])
            assert data == {"role_id": str(role.id), "menu_ids": []}
    else:
        db.commit.assert_not_awaited()
        db.flush.assert_not_awaited()
        menu_write.assert_not_awaited()
        audit.assert_not_awaited()
        publish.assert_not_awaited()
