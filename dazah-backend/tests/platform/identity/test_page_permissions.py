from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.platform.identity import page_permissions, rbac
from app.platform.identity.deps import require_module_view
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    FIRST_BATCH_MODULES,
    PAGES_BY_KEY,
    PAGES_BY_MODULE,
    canonical_page_key,
    get_page_definition,
    normalize_permissions,
    page_key_for_route,
    sensitive_action_for_request,
)
from app.platform.identity.schemas import (
    EffectivePageGrantOut,
    PageDataScopeInput,
    PageGrantInput,
    PagePermissionHealthRemediationRequest,
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
        active_users: list[object] | None = None,
        user_grants_by_user: dict[object, list[object]] | None = None,
    ) -> None:
        self.role_grants = role_grants or []
        self.user_grants = user_grants or []
        self.active_users = active_users or []
        self.user_grants_by_user = user_grants_by_user
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def list_role_grants(self, _db: object, **_kwargs: object) -> list[object]:
        self._called("list_role_grants")
        return self.role_grants

    async def list_user_grants(self, _db: object, **_kwargs: object) -> list[object]:
        self._called("list_user_grants")
        if self.user_grants_by_user is not None:
            return self.user_grants_by_user.get(_kwargs.get("user_id"), [])
        return self.user_grants

    async def list_user_grants_for_users(
        self, _db: object, **_kwargs: object
    ) -> list[object]:
        self._called("list_user_grants_for_users")
        if self.user_grants_by_user is None:
            return self.user_grants
        return [
            grant
            for user_id in _kwargs.get("user_ids", [])
            for grant in self.user_grants_by_user.get(user_id, [])
        ]

    async def list_active_users(self, _db: object) -> list[object]:
        self._called("list_active_users")
        return self.active_users

    async def list_all_role_grants(self, _db: object) -> list[object]:
        return self.role_grants

    async def list_all_user_grants(self, _db: object) -> list[object]:
        return self.user_grants

    async def list_roles_by_ids(self, _db: object, **_kwargs: object) -> list[object]:
        role_ids = set(_kwargs.get("role_ids", []))
        return [SimpleNamespace(id=role_id, name="人事经办员") for role_id in role_ids]

    async def list_users_by_ids(self, _db: object, **_kwargs: object) -> list[object]:
        return []

    async def department_labels(self, _db: object) -> dict[str, str]:
        return {}


@pytest.mark.asyncio
async def test_user_permission_output_uses_live_integration_checks() -> None:
    service = PagePermissionService(repo=_PageRepo())
    service.effective_grants = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service.integration_gaps = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda db, module_code: ["接口绑定缺失"]
        if module_code == "hr" else []
    )
    user = SimpleNamespace(id=uuid4(), grant_version=0)
    result = await service.user_permissions_out(None, user=user)
    assert result.module_checks["hr"] == "incomplete"
    assert result.module_checks["warehouse"] == "passed"


@pytest.mark.asyncio
async def test_system_admin_has_all_pages_even_with_explicit_denial(monkeypatch):
    monkeypatch.setattr(rbac, "resolve_user_roles", AsyncMock(return_value=[]))
    repo = _PageRepo(
        user_grants=[
            SimpleNamespace(page_key="hr:employee-management:profile", permissions=[])
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


@pytest.mark.asyncio
async def test_role_preview_uses_final_multi_source_grants_and_user_overrides(
    monkeypatch,
):
    role = SimpleNamespace(
        id=uuid4(), name="质量经办", code="quality-operator", grant_version=4
    )
    affected = SimpleNamespace(
        id=uuid4(), name="受影响用户", role="user", feishu_department_ids=None
    )
    overridden = SimpleNamespace(
        id=uuid4(), name="覆盖用户", role="user", feishu_department_ids=None
    )
    exact_deny = SimpleNamespace(
        user_id=overridden.id,
        page_key="hr:employee-management:profile",
        permissions=[],
        sensitive_actions=[],
        scope_type="department_tree",
        department_ids=[],
    )
    repo = _PageRepo(
        active_users=[affected, overridden],
        user_grants_by_user={overridden.id: [exact_deny]},
    )
    monkeypatch.setattr(
        rbac,
        "resolve_users_roles",
        AsyncMock(return_value={affected.id: [role], overridden.id: [role]}),
    )
    preview = await PagePermissionService(repo=repo).role_permissions_preview(
        None,
        role=role,
        module_access_mode="all",
        proposed_grants=[
            {
                "page_key": "hr:employee-management:profile",
                "permissions": ["access", "query"],
                "sensitive_actions": [],
                "scope_type": "department_tree",
                "department_ids": [],
            }
        ],
    )
    assert preview.member_count == 2
    assert preview.affected_user_count == 1
    assert preview.expanded_user_count == 1
    assert preview.users_with_overrides == 1
    assert [item.user_name for item in preview.affected_user_samples] == ["受影响用户"]
    assert repo.calls["list_user_grants_for_users"] == 1
    assert repo.calls.get("list_user_grants", 0) == 0
    assert repo.calls["list_role_grants"] == 2


def test_page_catalog_uses_stable_qualified_menu_keys() -> None:
    assert FIRST_BATCH_MODULES == {"hr", "warehouse", "quality", "procurement"}
    assert all(PAGES_BY_MODULE[module] for module in FIRST_BATCH_MODULES)
    assert "hr:employee-management:profile" in PAGES_BY_KEY
    assert page_key_for_route("/hr/profile") == "hr:employee-management:profile"
    assert all(page.route_path for page in PAGES_BY_KEY.values())


def test_reviewed_module_landing_routes_resolve_to_active_leaf_pages() -> None:
    assert page_key_for_route("/hr/employee-management") == (
        "hr:employee-management:profile"
    )
    assert page_key_for_route("/warehouse/materials/dashboard") == (
        "warehouse:materials:raw-summary"
    )
    assert page_key_for_route("/registration/project") == (
        "registration:project:project-ledger:international-associated-review"
    )
    assert page_key_for_route("/registration/validation-audit/task-1") == (
        "registration:project:declaration-progress:international-planned-in-progress"
    )


def test_legacy_warehouse_hardware_menu_keys_resolve_to_current_page_identity() -> None:
    legacy = "warehouse:hardware:hardware-101-1-workshop"
    current = "warehouse:hardware:hardware-hardware-101-1-workshop"

    assert canonical_page_key(legacy) == current
    assert get_page_definition(legacy) == PAGES_BY_KEY[current]


def test_legacy_warehouse_product_menu_keys_resolve_to_current_page_identity() -> None:
    legacy = "warehouse:product:product-details:product-detail-l-phenylalanine"
    current = (
        "warehouse:product-inventory:product-details:product-detail-l-phenylalanine"
    )

    assert canonical_page_key(legacy) == current
    assert get_page_definition(legacy) == PAGES_BY_KEY[current]


@pytest.mark.asyncio
async def test_missing_reviewed_module_rollout_is_pending_review() -> None:
    repo = _PageRepo()
    repo.get_rollout = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    result = await PagePermissionService(repo=repo).rollout_out(
        None, module_code="registration"
    )

    assert result.status == "draft"
    assert result.version == 0


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


def test_sensitive_action_expiry_requires_an_action() -> None:
    with pytest.raises(ValidationError):
        PageGrantInput(
            page_key="hr:employee-management:profile",
            sensitive_actions_expires_at=datetime.now(UTC) + timedelta(days=1),
        )


def test_sensitive_action_is_additive_to_ordinary_operation() -> None:
    service = PagePermissionService(repo=_PageRepo())  # type: ignore[arg-type]
    normalized = service.normalize_inputs(
        [
            PageGrantInput(
                page_key="hr:employee-management:profile",
                permissions=["access"],
                sensitive_actions=["delete"],
            )
        ],
        allow_inherit=True,
    )

    assert normalized[0]["permissions"] == ["access", "query", "operate"]
    assert normalized[0]["sensitive_actions"] == ["delete"]


@pytest.mark.asyncio
async def test_expired_sensitive_action_stops_authorizing(monkeypatch) -> None:
    role = SimpleNamespace(id=uuid4(), code="hr_operator", name="人事经办员")
    monkeypatch.setattr(rbac, "resolve_user_roles", AsyncMock(return_value=[role]))
    repo = _PageRepo(
        role_grants=[
            SimpleNamespace(
                role_id=role.id,
                page_key="hr:employee-management:profile",
                permissions=["operate"],
                sensitive_actions=["delete"],
                sensitive_actions_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                scope_type="department_tree",
                department_ids=[],
            )
        ]
    )

    grants = await PagePermissionService(repo=repo).effective_grants(
        None, user=SimpleNamespace(id=uuid4(), role="user")
    )
    grant = next(
        item for item in grants if item.page_key == "hr:employee-management:profile"
    )
    assert grant.permissions == ["access", "query", "operate"]
    assert grant.sensitive_actions == []
    assert grant.sensitive_action_expirations == {}


@pytest.mark.asyncio
async def test_health_check_reports_sensitive_action_without_expiry(
    monkeypatch,
) -> None:
    role_id = uuid4()
    repo = _PageRepo(
        role_grants=[
            SimpleNamespace(
                role_id=role_id,
                page_key="hr:employee-management:profile",
                permissions=["operate"],
                sensitive_actions=["delete"],
                sensitive_actions_expires_at=None,
                scope_type="department_tree",
                department_ids=[],
            )
        ]
    )
    monkeypatch.setattr(rbac, "resolve_users_roles", AsyncMock(return_value={}))

    health = await PagePermissionService(repo=repo).permission_health(None)

    assert health.issue_count == 1
    assert health.warning_count == 1
    assert health.issues[0].code == "sensitive_without_expiry"
    assert health.issues[0].target_id == role_id
    assert health.issues[0].remediation == "edit"
    assert health.issues[0].grant_version == 0


@pytest.mark.asyncio
async def test_health_missing_module_access_respects_access_mode(monkeypatch) -> None:
    user_id = uuid4()
    grant = SimpleNamespace(
        user_id=user_id,
        page_key="hr:employee-management:profile",
        permissions=["query"],
        sensitive_actions=[],
        sensitive_actions_expires_at=None,
        scope_type="department_tree",
        department_ids=[],
    )
    repo = _PageRepo(user_grants=[grant])
    user = SimpleNamespace(id=user_id, name="员工", role="user", grant_version=0)
    monkeypatch.setattr(repo, "list_users_by_ids", AsyncMock(return_value=[user]))
    monkeypatch.setattr(rbac, "resolve_users_roles", AsyncMock(return_value={}))
    monkeypatch.setattr(
        page_permissions.PermissionGrantRepository,
        "list_module_access_by_user",
        AsyncMock(return_value={}),
    )
    service = PagePermissionService(repo=repo)
    monkeypatch.setattr(service, "effective_grants", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        page_permissions, "get_settings",
        lambda: SimpleNamespace(effective_module_access_mode="all"),
    )
    assert not (await service.permission_health(None)).issues
    monkeypatch.setattr(
        page_permissions, "get_settings",
        lambda: SimpleNamespace(effective_module_access_mode="roles"),
    )
    issues = (await service.permission_health(None)).issues
    assert [issue.code for issue in issues] == ["missing_module_access"]


@pytest.mark.asyncio
async def test_health_remediation_removes_a_retired_role_grant(monkeypatch) -> None:
    from app.platform.identity import rbac_api

    role_id = uuid4()
    actor = SimpleNamespace(id=uuid4(), role="admin")
    role = SimpleNamespace(
        id=role_id, code="quality_operator", grant_version=2, updated_by=None
    )
    grant = SimpleNamespace(
        id=uuid4(),
        role_id=role_id,
        page_key="retired:page",
        permissions=["query"],
        sensitive_actions=[],
        sensitive_actions_expires_at=None,
        scope_type="department_tree",
        department_ids=[],
        updated_by=None,
    )
    repo = SimpleNamespace(
        get_role_for_update=AsyncMock(return_value=role),
        get_role_grant_for_update=AsyncMock(return_value=grant),
        list_role_grants=AsyncMock(side_effect=[[grant], []]),
        remove_grant=AsyncMock(),
    )
    service = SimpleNamespace(
        permission_health=AsyncMock(
            return_value=SimpleNamespace(
                issues=[
                    SimpleNamespace(
                        code="retired_page",
                        target_type="role",
                        target_id=role_id,
                        page_key="retired:page",
                    )
                ]
            )
        )
    )
    monkeypatch.setattr(rbac_api, "PagePermissionRepository", lambda: repo)
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    monkeypatch.setattr(
        rbac_api, "PermissionGrantRepository", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(rbac_api, "_assert_not_own_role", AsyncMock())
    monkeypatch.setattr(rbac_api, "_bump_all_user_grant_versions", AsyncMock())
    monkeypatch.setattr(rbac_api, "_audit", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", AsyncMock())
    db = AsyncMock()

    response = await rbac_api.remediate_page_permission_health_issue(
        PagePermissionHealthRemediationRequest(
            code="retired_page",
            target_type="role",
            target_id=role_id,
            page_key="retired:page",
            expected_grant_version=2,
            reason="清理停用页面",
        ),
        actor,
        db,
    )

    assert json.loads(response.body)["data"]["grant_version"] == 3
    repo.remove_grant.assert_awaited_once_with(db, grant)
    db.commit.assert_awaited_once()


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
    assert [item.role_name for item in employee.role_sources] == [
        "人事查看员",
        "人事经办员",
    ]
    assert "合并 2 个角色" in employee.resolution[0]

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
    assert employee.source_role_names == ["人事查看员", "人事经办员"]
    assert "用户覆盖完整替换角色基线" in employee.resolution[0]

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
async def test_saved_page_policy_rejects_missing_or_insufficient_page_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform.identity import deps

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
async def test_saved_page_grant_cannot_bypass_direct_module_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.platform.identity import deps

    monkeypatch.setattr(
        deps.PermissionGrantRepository,
        "has_module_view",
        AsyncMock(return_value=False),
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
    allowed = await rbac_api.simulate_page_permission(
        PagePermissionSimulationRequest(
            user_id=user.id,
            page_key="hr:employee-management:profile",
            permission="query",
        ),
        SimpleNamespace(role="admin"),
        Any,  # type: ignore[arg-type]
        SimpleNamespace(effective_module_access_mode="all"),
    )
    assert "实际接口还需核对" in json.loads(allowed.body)["data"]["reason"]
