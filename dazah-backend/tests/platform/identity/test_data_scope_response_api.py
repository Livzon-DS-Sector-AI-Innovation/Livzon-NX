"""Exercise data-scope ORM conversion through real routes without a database."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import rbac_api
from app.platform.identity.models import DataScopeRule, User


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_save_data_scope_serializes_orm_and_commits(
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    actor = User(id=uuid4(), name="测试管理员", role="admin")
    rule = DataScopeRule(
        id=uuid4(),
        user_id=uuid4(),
        role_id=None,
        scope_type="all",
        department_names=None,
    )
    db = AsyncMock()
    repo = AsyncMock()
    repo.get_data_scope_rule_by_target.return_value = rule if existing else None
    repo.create_data_scope_rule.return_value = rule
    repo.update_data_scope_rule.return_value = rule
    monkeypatch.setattr(rbac_api, "RbacRepository", lambda: repo)
    audit = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "publish_data_scope_changed", publish)
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/identity/admin/data-scopes",
            json={
                "user_id": str(rule.user_id),
                "scope_type": "all",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"] == {
            "id": str(rule.id),
            "user_id": str(rule.user_id),
            "role_id": None,
            "scope_type": "all",
            "department_names": [],
        }
        db.commit.assert_awaited_once()
        assert audit.await_args.kwargs["new_value"] == response.json()["data"]
        publish.assert_awaited_once_with("user", rule.user_id)
        db.commit.reset_mock()
        invalid = await client.post(
            "/api/v1/identity/admin/data-scopes",
            json={
                "user_id": str(rule.user_id),
                "scope_type": "departments",
                "department_names": [],
            },
        )
        assert invalid.status_code == 422
        db.commit.assert_not_awaited()

        # List, update and delete share the same ORM response conversion.
        rule.scope_type = "departments"
        rule.department_names = '["质量部"]'
        repo.list_data_scope_rules.return_value = [rule]
        repo.get_data_scope_rule_by_id.return_value = rule
        listed = await client.get("/api/v1/identity/admin/data-scopes")
        assert listed.status_code == 200
        assert listed.json()["data"][0]["department_names"] == ["质量部"]
        updated = await client.put(
            f"/api/v1/identity/admin/data-scopes/{rule.id}",
            json={"scope_type": "departments", "department_names": ["质量部"]},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["department_names"] == ["质量部"]
        deleted = await client.delete(
            f"/api/v1/identity/admin/data-scopes/{rule.id}",
        )
        assert deleted.status_code == 200
        repo.soft_delete_data_scope_rule.assert_awaited_once_with(db, rule)
        assert db.commit.await_count == 2
