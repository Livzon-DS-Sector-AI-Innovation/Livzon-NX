from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.platform.identity import rbac_api
from app.platform.identity.schemas import (
    DataScopeRuleCreateRequest,
    DataScopeRuleResponse,
    DataScopeRuleUpdateRequest,
    RolePermissionsRequest,
)


class _Result:
    def __init__(self, values: list[object] | None = None) -> None:
        self.values = values or []

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values


class _Db:
    def __init__(self, values: list[object] | None = None) -> None:
        self.execute = AsyncMock(return_value=_Result(values))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


def _role(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "name": "质量管理员",
        "code": "quality_admin",
        "description": "质量模块管理员",
        "is_system": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(**overrides: object) -> DataScopeRuleResponse:
    values: dict[str, object] = {
        "id": uuid4(),
        "role_id": uuid4(),
        "user_id": None,
        "scope_type": "departments",
        "department_names": '["质量部"]',
    }
    values.update(overrides)
    return DataScopeRuleResponse(**values)


def _patch_common(
    monkeypatch: pytest.MonkeyPatch, role: object
) -> tuple[AsyncMock, AsyncMock]:
    monkeypatch.setattr(rbac_api, "_get_role_or_404", AsyncMock(return_value=role))
    audit = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", publish)
    return audit, publish


@pytest.mark.asyncio
async def test_set_role_permissions_deduplicates_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = _role()
    permission_id = uuid4()
    repo = SimpleNamespace(
        list_role_permission_codes=AsyncMock(return_value=["quality:read"]),
        set_role_permissions=AsyncMock(),
    )
    monkeypatch.setattr(rbac_api, "RbacRepository", lambda: repo)
    audit, publish = _patch_common(monkeypatch, role)
    db = _Db([permission_id])
    current_user = SimpleNamespace(id=uuid4())

    response = await rbac_api.set_role_permissions(
        role.id,
        RolePermissionsRequest(permission_ids=[permission_id, permission_id]),
        current_user,
        db,
    )

    assert response.status_code == 200
    repo.set_role_permissions.assert_awaited_once_with(db, role.id, [permission_id])
    audit.assert_awaited_once()
    publish.assert_awaited_once()
    assert db.commit.await_count == 1

    db = _Db([])
    with pytest.raises(HTTPException) as exc_info:
        await rbac_api.set_role_permissions(
            role.id,
            RolePermissionsRequest(permission_ids=[permission_id]),
            current_user,
            db,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_data_scope_create_update_delete_and_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = _role()
    rule = _rule(role_id=role.id)
    new_rule = _rule(role_id=role.id)

    class _Repo:
        async def list_data_scope_rules(self, _db: object) -> list[object]:
            return [rule]

        async def get_data_scope_rule_by_target(
            self, _db: object, **_kwargs: object
        ) -> object:
            return None

        async def create_data_scope_rule(self, _db: object, **kwargs: object) -> object:
            for key, value in kwargs.items():
                setattr(new_rule, key, value)
            return new_rule

        async def update_data_scope_rule(
            self, _db: object, target: object, **kwargs: object
        ) -> object:
            for key, value in kwargs.items():
                setattr(target, key, value)
            return target

        async def get_data_scope_rule_by_id(
            self, _db: object, _rule_id: object
        ) -> object:
            return rule

        async def soft_delete_data_scope_rule(
            self, _db: object, target: object
        ) -> None:
            target.scope_type = "all"
            target.department_names = None

    monkeypatch.setattr(rbac_api, "RbacRepository", _Repo)
    audit = AsyncMock()
    publish_scope = AsyncMock()
    monkeypatch.setattr(rbac_api, "_audit", audit)
    monkeypatch.setattr(rbac_api, "publish_data_scope_changed", publish_scope)
    current_user = SimpleNamespace(id=uuid4())

    listed = await rbac_api.list_data_scope_rules(current_user, _Db())
    assert listed.status_code == 200

    created = await rbac_api.create_data_scope_rule(
        DataScopeRuleCreateRequest(
            role_id=role.id, scope_type="departments", department_names=["质量部"]
        ),
        current_user,
        _Db(),
    )
    assert created.status_code == 200
    assert new_rule.department_names == '["质量部"]'

    updated = await rbac_api.update_data_scope_rule(
        rule.id,
        DataScopeRuleUpdateRequest(scope_type="all"),
        current_user,
        _Db(),
    )
    assert updated.status_code == 200
    assert rule.department_names is None

    deleted = await rbac_api.delete_data_scope_rule(rule.id, current_user, _Db())
    assert deleted.status_code == 200
    assert audit.await_count == 3
    assert publish_scope.await_count == 3


@pytest.mark.asyncio
async def test_data_scope_existing_target_and_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = _role()
    existing = _rule(role_id=role.id)

    class _Repo:
        async def get_data_scope_rule_by_target(
            self, _db: object, **_kwargs: object
        ) -> object:
            return existing

        async def update_data_scope_rule(
            self, _db: object, target: object, **kwargs: object
        ) -> object:
            for key, value in kwargs.items():
                setattr(target, key, value)
            return target

    monkeypatch.setattr(rbac_api, "RbacRepository", _Repo)
    monkeypatch.setattr(rbac_api, "_audit", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_data_scope_changed", AsyncMock())
    current_user = SimpleNamespace(id=uuid4())
    response = await rbac_api.create_data_scope_rule(
        DataScopeRuleCreateRequest(
            role_id=role.id, scope_type="departments", department_names=["人事部"]
        ),
        current_user,
        _Db(),
    )
    assert response.status_code == 200
    assert existing.department_names == '["人事部"]'

    class _MissingRepo:
        async def get_data_scope_rule_by_id(
            self, _db: object, _rule_id: object
        ) -> None:
            return None

    monkeypatch.setattr(rbac_api, "RbacRepository", _MissingRepo)
    with pytest.raises(HTTPException) as exc_info:
        await rbac_api.update_data_scope_rule(
            uuid4(), DataScopeRuleUpdateRequest(), current_user, _Db()
        )
    assert exc_info.value.status_code == 404

    incomplete = _rule()

    class _IncompleteRepo:
        async def get_data_scope_rule_by_id(
            self, _db: object, _rule_id: object
        ) -> object:
            return incomplete

    monkeypatch.setattr(rbac_api, "RbacRepository", _IncompleteRepo)
    with pytest.raises(HTTPException) as exc_info:
        await rbac_api.update_data_scope_rule(
            uuid4(),
            DataScopeRuleUpdateRequest(scope_type="departments", department_names=None),
            current_user,
            _Db(),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_rbac_helpers_and_role_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = _role()
    payload = rbac_api._role_payload(role, ["quality:read"])
    assert payload["permissions"] == ["quality:read"]

    class _Missing:
        async def get_role_by_id(self, _db: object, _role_id: object) -> None:
            return None

    monkeypatch.setattr(rbac_api, "RbacRepository", _Missing)
    with pytest.raises(HTTPException) as exc_info:
        await rbac_api._get_role_or_404(_Db(), uuid4())
    assert exc_info.value.status_code == 404
