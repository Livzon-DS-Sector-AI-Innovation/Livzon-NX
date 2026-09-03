from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.platform.identity import rbac
from app.platform.identity.deps import require_module_view
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    FIRST_BATCH_MODULES,
    PAGES_BY_KEY,
    PAGES_BY_MODULE,
    normalize_permissions,
    page_key_for_route,
    sensitive_action_for_request,
)
from app.platform.identity.schemas import (
    EffectivePageGrantOut,
    PageDataScopeInput,
    PageGrantInput,
    PagePermissionSimulationRequest,
)


class _PageRepo:
    async def active_page_keys(self, _db):
        return set(PAGES_BY_KEY)

    def __init__(
        self,
        *,
        role_grants: list[object] | None = None,
        user_grants: list[object] | None = None,
    ) -> None:
        self.role_grants = role_grants or []
        self.user_grants = user_grants or []

    async def list_role_grants(self, _db: object, **_kwargs: object) -> list[object]:
        return self.role_grants

    async def list_user_grants(self, _db: object, **_kwargs: object) -> list[object]:
        return self.user_grants


@pytest.mark.asyncio
async def test_system_admin_has_all_pages_even_with_explicit_denial(monkeypatch):
    monkeypatch.setattr(rbac, "resolve_user_roles", AsyncMock(return_value=[]))
    repo = _PageRepo(
        user_grants=[
            SimpleNamespace(
                page_key="hr:employee-management:profile", permissions=[]
            )
        ]
    )
    grants = await PagePermissionService(repo=repo).effective_grants(
        None, user=SimpleNamespace(id=uuid4(), role="admin")
    )
    assert len(grants) == len(PAGES_BY_KEY)
    for grant in grants:
        assert grant.permissions == ["access", "query", "operate"]
        assert grant.sensitive_actions == [
            action.key for action in PAGES_BY_KEY[grant.page_key].sensitive_actions
        ]
        assert grant.data_scope.scope_type in {"all", "not_applicable"}
        assert grant.source_role_names == ["系统管理员"]


def test_page_catalog_uses_stable_qualified_menu_keys() -> None:
    assert FIRST_BATCH_MODULES == {"hr", "warehouse", "quality", "procurement"}
    assert all(PAGES_BY_MODULE[module] for module in FIRST_BATCH_MODULES)
    assert "hr:employee-management:profile" in PAGES_BY_KEY
    assert page_key_for_route("/hr/profile") == "hr:employee-management:profile"
    assert all(page.route_path for page in PAGES_BY_KEY.values())


def test_page_permission_dependency_is_normalized() -> None:
    assert normalize_permissions(["operate"]) == ("access", "query", "operate")
    assert normalize_permissions(["query"]) == ("access", "query")
    assert normalize_permissions([]) == ()
    with pytest.raises(ValueError, match="未知页面权限"):
        normalize_permissions(["raw_api_code"])


def test_sensitive_business_actions_are_derived_from_server_request() -> None:
    assert sensitive_action_for_request("DELETE", "/api/v1/hr/employees/1") == "delete"
    assert sensitive_action_for_request("POST", "/api/v1/procurement/approve") == (
        "approve"
    )
    assert sensitive_action_for_request("POST", "/api/v1/quality/import") == (
        "bulk_import"
    )
    assert sensitive_action_for_request("GET", "/api/v1/quality/export") == (
        "sensitive_export"
    )


def test_livzon_tool_catalog_exposes_page_permission_binding() -> None:
    from app.modules.agent.tool_registration import ensure_agent_tools_registered
    from app.modules.agent.tools import tool_registry

    ensure_agent_tools_registered()
    quality_tool = tool_registry.require("quality.list_deviations").public_dict()
    assert quality_tool["page_keys"] == ["quality:deviations:deviation-ledger"]
    assert quality_tool["sensitive_action"] is None
    approval_tool = tool_registry.require(
        "procurement.approve_purchase_request"
    ).public_dict()
    assert approval_tool["page_keys"]
    assert approval_tool["sensitive_action"] == "approve"
    assert approval_tool["workflow_allowed"] is False


def test_page_scope_schema_rejects_ambiguous_department_selection() -> None:
    with pytest.raises(ValidationError, match="至少选择一个部门"):
        PageDataScopeInput(scope_type="departments")
    with pytest.raises(ValidationError, match="仅指定部门范围"):
        PageDataScopeInput(
            scope_type="department_tree", department_ids=["od-forbidden"]
        )


def test_page_input_rejects_unknown_sensitive_action_and_unsupported_scope() -> None:
    service = PagePermissionService(repo=_PageRepo())  # type: ignore[arg-type]
    with pytest.raises(HTTPException, match="不支持操作"):
        service.normalize_inputs(
            [
                PageGrantInput(
                    page_key="hr:employee-management:profile",
                    sensitive_actions=["POST_/raw/api"],
                )
            ],
            allow_inherit=True,
        )
    with pytest.raises(HTTPException, match="不支持数据范围"):
        service.normalize_inputs(
            [
                PageGrantInput(
                    page_key="hr:employee-management:profile",
                    data_scope=PageDataScopeInput(scope_type="self"),
                )
            ],
            allow_inherit=True,
        )


@pytest.mark.asyncio
async def test_role_union_and_user_exact_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_role_id = uuid4()
    second_role_id = uuid4()
    roles = [
        SimpleNamespace(id=first_role_id, code="hr_reader", name="人事查看员"),
        SimpleNamespace(id=second_role_id, code="hr_operator", name="人事经办员"),
    ]

    async def _roles(_db: object, _user_id: object) -> list[object]:
        return roles

    monkeypatch.setattr(rbac, "resolve_user_roles", _roles)
    role_grants = [
        SimpleNamespace(
            role_id=first_role_id,
            page_key="hr:employee-management:profile",
            permissions=["query"],
            sensitive_actions=[],
            scope_type="department_tree",
            department_ids=[],
        ),
        SimpleNamespace(
            role_id=second_role_id,
            page_key="hr:employee-management:profile",
            permissions=["operate"],
            sensitive_actions=["delete"],
            scope_type="all",
            department_ids=[],
        ),
    ]
    user = SimpleNamespace(id=uuid4(), role="user")
    service = PagePermissionService(
        repo=_PageRepo(role_grants=role_grants)  # type: ignore[arg-type]
    )
    grants = await service.effective_grants(Any, user=user)  # type: ignore[arg-type]
    employee = next(
        item for item in grants if item.page_key == "hr:employee-management:profile"
    )
    assert employee.permissions == ["access", "query", "operate"]
    assert employee.sensitive_actions == ["delete"]
    assert employee.data_scope.scope_type == "all"
    assert employee.source_role_names == ["人事查看员", "人事经办员"]

    service = PagePermissionService(
        repo=_PageRepo(  # type: ignore[arg-type]
            role_grants=role_grants,
            user_grants=[
                SimpleNamespace(
                    page_key="hr:employee-management:profile",
                    permissions=[],
                    sensitive_actions=[],
                    scope_type="department_tree",
                    department_ids=[],
                )
            ],
        )
    )
    denied = await service.effective_grants(Any, user=user)  # type: ignore[arg-type]
    employee = next(
        item for item in denied if item.page_key == "hr:employee-management:profile"
    )
    assert employee.permissions == []
    assert employee.source == "none"
    assert employee.source_role_names == []

    baseline = await service.effective_grants(
        Any, user=user, include_user_overrides=False
    )
    assert baseline[0].permissions == ["access", "query", "operate"]
    assert baseline[0].sensitive_actions == ["delete"]
    assert baseline[0].source == "role"
    service.repo.user_grants[0].scope_type = "not_applicable"
    # A policy change invalidating a custom scope cannot reveal the role baseline.
    assert await service.effective_grants(Any, user=user) == []


@pytest.mark.asyncio
async def test_ordinary_user_has_no_business_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _roles(_db: object, _user_id: object) -> list[object]:
        return []

    class _Result:
        def scalar_one_or_none(self) -> None:
            return None

        def all(self) -> list[object]:
            return []

        def scalars(self) -> _Result:
            return self

    class _Db:
        async def execute(self, _statement: object) -> _Result:
            return _Result()

    monkeypatch.setattr(rbac, "resolve_user_roles", _roles)
    # A user not matching the system-administrator query has no implicit grant.
    assert await rbac.resolve_user_permissions(_Db(), uuid4()) == []  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_enforced_module_rejects_missing_or_insufficient_page_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform.identity import deps

    class _RolloutRepo:
        async def get_rollout(self, _db: object, **_kwargs: object) -> object:
            return SimpleNamespace(status="enforced")

    class _Service:
        async def effective_grants(
            self, _db: object, **_kwargs: object
        ) -> list[object]:
            return [
                EffectivePageGrantOut(
                    page_key="hr:employee-management:profile",
                    module_code="hr",
                    permissions=["access"],
                    sensitive_actions=[],
                    data_scope=PageDataScopeInput(scope_type="department_tree"),
                    source="user",
                )
            ]

    monkeypatch.setattr(deps, "PagePermissionRepository", _RolloutRepo)
    monkeypatch.setattr(deps, "PagePermissionService", _Service)
    monkeypatch.setattr(
        deps.PermissionGrantRepository,
        "has_module_view",
        AsyncMock(return_value=True),
    )
    dependency = require_module_view("hr")
    user = SimpleNamespace(id=uuid4(), role="user")
    settings = SimpleNamespace(effective_module_access_mode="roles")

    missing = Request(
        {"type": "http", "method": "GET", "path": "/api/v1/hr/employees", "headers": []}
    )
    with pytest.raises(HTTPException) as exc_info:
        await dependency(missing, user, Any, settings)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 400

    access_only = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/hr/employees",
                "headers": [(b"x-dazah-page-path", b"/hr/profile")],
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        await dependency(access_only, user, Any, settings)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_enforced_page_grant_cannot_bypass_direct_module_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform.identity import deps

    monkeypatch.setattr(
        deps.PermissionGrantRepository,
        "has_module_view",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        deps.PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    page_grants = AsyncMock(
        return_value=[
            EffectivePageGrantOut(
                page_key="hr:employee-management:profile",
                module_code="hr",
                permissions=["access", "query"],
                sensitive_actions=[],
                data_scope=PageDataScopeInput(scope_type="department_tree"),
                source="user",
            )
        ]
    )
    monkeypatch.setattr(deps.PagePermissionService, "effective_grants", page_grants)
    dependency = require_module_view("hr")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/hr/employees",
            "headers": [(b"x-dazah-page-key", b"hr:employee-management:profile")],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(
            request,
            SimpleNamespace(id=uuid4(), role="user"),
            Any,  # type: ignore[arg-type]
            SimpleNamespace(effective_module_access_mode="roles"),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "未获授权访问模块：hr"
    page_grants.assert_not_awaited()


@pytest.mark.asyncio
async def test_permission_verification_reports_missing_module_access_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform.identity import rbac_api

    user = SimpleNamespace(id=uuid4(), role="user")
    monkeypatch.setattr(
        rbac_api,
        "_get_target_user_or_404",
        AsyncMock(return_value=user),
    )

    class _Service:
        async def effective_grants(
            self, _db: object, **_kwargs: object
        ) -> list[object]:
            return [
                EffectivePageGrantOut(
                    page_key="hr:employee-management:profile",
                    module_code="hr",
                    permissions=["access", "query"],
                    sensitive_actions=[],
                    data_scope=PageDataScopeInput(scope_type="department_tree"),
                    source="user",
                )
            ]

        async def is_super_admin(self, _db: object, **_kwargs: object) -> bool:
            return False

    monkeypatch.setattr(rbac_api, "PagePermissionService", _Service)
    monkeypatch.setattr(
        rbac_api.PermissionGrantRepository,
        "has_module_view",
        AsyncMock(return_value=False),
    )
    response = await rbac_api.simulate_page_permission(
        PagePermissionSimulationRequest(
            user_id=user.id,
            page_key="hr:employee-management:profile",
            permission="query",
        ),
        SimpleNamespace(role="admin"),
        Any,  # type: ignore[arg-type]
        SimpleNamespace(effective_module_access_mode="roles"),
    )
    payload = json.loads(response.body)

    assert payload["data"]["allowed"] is False
    assert payload["data"]["reason"] == "当前账号未获得所属模块访问权限"
