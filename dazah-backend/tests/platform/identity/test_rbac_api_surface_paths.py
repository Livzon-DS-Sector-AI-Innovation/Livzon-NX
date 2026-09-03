from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.platform.identity import rbac_api
from app.platform.identity.data_scope import DepartmentScope
from app.platform.identity.schemas import (
    AssignUserRoleRequest,
    DeptRuleCreateRequest,
    DeptRuleResponse,
    MenuCreateRequest,
    MenuUpdateRequest,
    PermissionSimulateRequest,
    RoleCreateRequest,
    RoleMenusRequest,
    RoleUpdateRequest,
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
        self.scalars = AsyncMock(return_value=_Result(values))
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


def _menu(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "key": "quality.records",
        "parent_id": None,
        "name": "质量记录",
        "type": "menu",
        "permission_code": "quality.read",
        "route_path": "/quality/records",
        "component_path": "quality/records/page",
        "icon": None,
        "sort_order": 1,
        "status": "active",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_rbac_role_user_department_and_menu_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = SimpleNamespace(id=uuid4(), role="admin")
    role = _role()
    role_updated = _role(id=role.id, name="质量主管")
    user = SimpleNamespace(
        id=uuid4(), name="张三", department="质量部", role="user", grant_version=0
    )
    dept_rule = DeptRuleResponse(
        id=uuid4(),
        role_id=role.id,
        feishu_department_id="dept-1",
        department_name="质量部",
    )
    repo = SimpleNamespace(
        get_role_by_code=AsyncMock(return_value=None),
        create_role=AsyncMock(return_value=role),
        update_role=AsyncMock(return_value=role_updated),
        soft_delete_role=AsyncMock(),
        list_role_permission_codes=AsyncMock(return_value=["quality.read"]),
        list_user_roles=AsyncMock(return_value=[role]),
        assign_user_role=AsyncMock(),
        remove_user_role=AsyncMock(return_value=True),
        list_dept_rules=AsyncMock(return_value=[dept_rule]),
        get_role_by_id=AsyncMock(return_value=role),
        create_dept_rule=AsyncMock(return_value=dept_rule),
        get_dept_rule_by_id=AsyncMock(return_value=dept_rule),
        soft_delete_dept_rule=AsyncMock(),
        list_roles=AsyncMock(return_value=[role]),
    )
    monkeypatch.setattr(rbac_api, "RbacRepository", lambda: repo)
    monkeypatch.setattr(
        rbac_api,
        "UserRepository",
        lambda: SimpleNamespace(
            list_all=AsyncMock(return_value=([user], 1)),
            get_by_id=AsyncMock(return_value=user),
        ),
    )
    monkeypatch.setattr(rbac_api, "_get_role_or_404", AsyncMock(return_value=role))
    monkeypatch.setattr(
        rbac_api, "_get_target_user_or_404", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(rbac_api, "_audit", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_permissions_changed", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", AsyncMock())
    outbox = AsyncMock()
    monkeypatch.setattr(
        rbac_api.PermissionGrantRepository, "create_outbox_event", outbox
    )

    assert (await rbac_api.list_roles(actor, _Db())).status_code == 200
    assert (await rbac_api.list_roles(actor, _Db())).status_code == 200
    assert (
        await rbac_api.create_role(
            RoleCreateRequest(name="新角色", code="new_role"), actor, _Db()
        )
    ).status_code == 200
    assert (
        await rbac_api.update_role(
            role.id, RoleUpdateRequest(name="质量主管"), actor, _Db()
        )
    ).status_code == 200
    assert (await rbac_api.delete_role(role.id, actor, _Db())).status_code == 200

    assert (
        await rbac_api.list_admin_users(actor, _Db(), keyword="张", offset=0, limit=20)
    ).status_code == 200
    assert (
        await rbac_api.assign_user_roles(
            user.id, AssignUserRoleRequest(role_ids=[role.id]), actor, _Db()
        )
    ).status_code == 200
    assert (
        await rbac_api.remove_user_role(user.id, role.id, actor, _Db())
    ).status_code == 200
    assert user.grant_version == 2
    assert [call.kwargs["grant_version"] for call in outbox.await_args_list] == [1, 2]

    assert (await rbac_api.list_dept_rules(actor, _Db())).status_code == 200
    assert (
        await rbac_api.create_dept_rule(
            DeptRuleCreateRequest(role_id=role.id, department_name="质量部"),
            actor,
            _Db(),
        )
    ).status_code == 200
    assert (
        await rbac_api.delete_dept_rule(dept_rule.id, actor, _Db())
    ).status_code == 200

    menu = _menu()
    menu_repo = SimpleNamespace(
        list_all=AsyncMock(return_value=[menu]),
        get_by_id=AsyncMock(return_value=menu),
        create=AsyncMock(return_value=menu),
        update=AsyncMock(return_value=menu),
        list_children=AsyncMock(return_value=[]),
        soft_delete=AsyncMock(),
        list_role_menu_ids=AsyncMock(return_value=[menu.id]),
        set_role_menus=AsyncMock(),
    )
    monkeypatch.setattr(rbac_api, "MenuRepository", lambda: menu_repo)
    assert (await rbac_api.list_menus(actor, _Db())).status_code == 200
    assert (
        await rbac_api.create_menu(
            MenuCreateRequest(name="新菜单", type="menu"), actor, _Db()
        )
    ).status_code == 200
    assert (
        await rbac_api.update_menu(
            menu.id, MenuUpdateRequest(name="更新菜单"), actor, _Db()
        )
    ).status_code == 200
    assert (await rbac_api.delete_menu(menu.id, actor, _Db())).status_code == 200
    assert (await rbac_api.get_role_menus(role.id, actor, _Db())).status_code == 200
    assert (
        await rbac_api.set_role_menus(
            role.id, RoleMenusRequest(menu_ids=[menu.id]), actor, _Db()
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_rbac_permission_preview_simulation_and_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = SimpleNamespace(id=uuid4(), role="admin")
    user = SimpleNamespace(
        id=uuid4(), name="李四", department="人事部", role="user", username="lisi"
    )
    role = _role()
    monkeypatch.setattr(
        rbac_api, "_get_target_user_or_404", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(rbac_api, "resolve_user_roles", AsyncMock(return_value=[role]))
    monkeypatch.setattr(
        rbac_api, "resolve_user_permissions", AsyncMock(return_value=["hr.read"])
    )
    monkeypatch.setattr(
        rbac_api, "resolve_user_menu_ids", AsyncMock(return_value=[uuid4()])
    )
    monkeypatch.setattr(
        rbac_api,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"人事部"})
        ),
    )
    response = await rbac_api.get_user_permission_preview(user.id, actor, _Db())
    assert response.status_code == 200

    monkeypatch.setattr(
        rbac_api,
        "check_access",
        Mock(
            return_value=SimpleNamespace(
                allowed=True, reason="ok", required="hr.read", note=None
            )
        ),
    )
    response = await rbac_api.simulate_permission(
        PermissionSimulateRequest(
            user_id=user.id,
            method="GET",
            path="/api/v1/hr/employees",
            department="人事部",
        ),
        actor,
        _Db(),
    )
    assert response.status_code == 200

    db = _Db([user])
    monkeypatch.setattr(
        rbac_api.PagePermissionRepository,
        "department_labels",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        rbac_api.PagePermissionRepository, "list_rollouts", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        rbac_api.PagePermissionService, "effective_grants", AsyncMock(return_value=[])
    )
    response = await rbac_api.export_permissions(actor, db)
    assert response.status_code == 200
    assert "姓名" in response.body.decode("utf-8-sig")  # type: ignore[union-attr]
    assert "菜单页面" in response.body.decode("utf-8-sig")
    assert "权限点" not in response.body.decode("utf-8-sig")
    assert "无页面授权" in response.body.decode("utf-8-sig")

    monkeypatch.setattr(rbac_api, "require_current_user", AsyncMock(return_value=actor))
    monkeypatch.setattr(
        rbac_api, "resolve_user_permissions", AsyncMock(return_value={"identity:admin"})
    )
    assert (
        await rbac_api.require_identity_admin(
            actor, Request({"type": "http", "method": "GET"}), _Db()
        )
    ).id == actor.id
