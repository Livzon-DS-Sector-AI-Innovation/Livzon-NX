from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import deps, page_policy, rbac
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.fixture(autouse=True)
def admin_mutation_lock(monkeypatch):
    # These route unit tests use a fake session; the real lock is covered by
    # test_authorization_core with independent PostgreSQL transactions.
    for module in ("api", "rbac_api"):
        monkeypatch.setattr(
            f"app.platform.identity.{module}.lock_authorization_actor",
            AsyncMock(side_effect=lambda db, actor: actor),
        )


@pytest.mark.asyncio
async def test_http_enforcement_uses_exact_route_and_page_binding(monkeypatch):
    user = SimpleNamespace(id=uuid4())

    async def grants(*args, **kwargs):
        return [
            EffectivePageGrantOut(
                page_key="hr:employee-management:profile",
                module_code="hr",
                permissions=["access", "query", "operate"],
                sensitive_actions=[],
                data_scope=PageDataScopeInput(scope_type="department_tree"),
                source="user",
            )
        ]

    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    monkeypatch.setattr(
        deps.PermissionGrantRepository,
        "has_module_view",
        AsyncMock(return_value=True),
    )
    # Test an absent contract explicitly; the real employee route is now reviewed.
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", ())
    app = FastAPI()
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="roles"
    )

    @app.get(
        "/api/v1/hr/employees/{employee_id}",
        dependencies=[Depends(deps.require_module_view("hr"))],
    )
    async def employee(employee_id: str):
        return {"id": employee_id}

    headers = {"X-Dazah-Page-Key": "hr:employee-management:profile"}
    path = "/api/v1/hr/employees/one"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(path)).status_code == 400
        # Same-module context cannot authorize an unregistered endpoint.
        assert (await client.get(path, headers=headers)).status_code == 403
        binding = page_policy.PageApiBinding(
            route_path="/api/v1/hr/employees/{employee_id}",
            method="GET",
            page_keys=("hr:employee-management:profile",),
            permission="query",
            scope_adapter="test_department_adapter",
        )
        monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", (binding,))
        response = await client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"id": "one"}
        other_page = next(
            page.page_key
            for page in page_policy.PAGES_BY_MODULE["hr"]
            if page.page_key != "hr:employee-management:profile"
        )
        response = await client.get(path, headers={"X-Dazah-Page-Key": other_page})
        assert response.status_code == 403
        assert "不允许调用" in response.json()["detail"]
        # Duplicate contracts must not silently select the first entry.
        monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", (binding, binding))
        assert (await client.get(path, headers=headers)).status_code == 403
        app.dependency_overrides[deps.get_current_user] = lambda: None
        assert (await client.get(path, headers=headers)).status_code == 401


def test_incomplete_first_batch_cannot_be_published(monkeypatch):
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", ())
    for module in page_policy.FIRST_BATCH_MODULES:
        assert page_policy.page_api_catalog_gaps(module)


def test_role_department_union_includes_own_department():
    assert PagePermissionService._merge_role_scopes(
        {"department_tree", "departments"},
        {"od-selected"},
        own_department_ids={"od-own"},
    ) == ("departments", ["od-own", "od-selected"])


@pytest.mark.asyncio
async def test_empty_role_grant_does_not_expand_other_role_scope(monkeypatch):
    roles = [
        SimpleNamespace(id=uuid4(), name="读取", code="reader"),
        SimpleNamespace(id=uuid4(), name="空授权", code="empty"),
    ]

    async def resolve_roles(*args):
        return roles

    class Repo:
        async def active_page_keys(self, db):
            return set(page_policy.PAGES_BY_KEY)

        async def list_role_grants(self, *args, **kwargs):
            return [
                SimpleNamespace(
                    page_key="hr:employee-management:profile",
                    role_id=role.id,
                    permissions=["query"] if index == 0 else [],
                    sensitive_actions=[],
                    scope_type="department_tree" if index == 0 else "all",
                    department_ids=[],
                )
                for index, role in enumerate(roles)
            ]

        async def list_user_grants(self, *args, **kwargs):
            return []

    monkeypatch.setattr(rbac, "resolve_user_roles", resolve_roles)
    service = PagePermissionService(repo=Repo())
    grants = await service.effective_grants(None, user=SimpleNamespace(id=uuid4()))
    assert grants[0].data_scope.scope_type == "department_tree"
    assert grants[0].source_role_names == ["读取"]


@pytest.mark.asyncio
async def test_preview_expires_after_permission_change_with_same_user_counts(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), grant_version=1)

    class Repo:
        async def active_page_keys(self, db):
            return set(page_policy.PAGES_BY_KEY)

        async def active_menu_page_catalog(self, db):
            return [
                ActiveMenuPage(
                    key=page.page_key,
                    name=page.page_name,
                    route_path=page.route_path,
                    root_key=page.page_key.split(":", 1)[0],
                )
                for page in page_policy.PAGES_BY_KEY.values()
            ]

        async def get_rollout(self, *args, **kwargs):
            return None

        async def list_active_users(self, *args, **kwargs):
            return [user]

        async def list_role_grants(self, *args, **kwargs):
            return []

        async def list_user_grants_for_users(self, *args, **kwargs):
            return []

    async def grants(*args, **kwargs):
        return []

    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    monkeypatch.setattr(
        rbac, "resolve_users_roles", AsyncMock(return_value={user.id: []})
    )
    service = PagePermissionService(repo=Repo())
    before = await service.rollout_preview(None, module_code="hr")
    user.grant_version += 1
    after = await service.rollout_preview(None, module_code="hr")
    assert before.user_count == after.user_count
    assert before.users_without_access == after.users_without_access
    assert before.preview_hash != after.preview_hash
    # Unrelated modules' tool pages are not falsely reported as invalid HR bindings.
    assert not any("工具页面绑定无效" in gap for gap in after.catalog_gaps)


@pytest.mark.asyncio
async def test_role_management_http_rejects_indirect_self_escalation(monkeypatch):
    from app.platform.identity import rbac_api

    # A delegated permission manager is not a full system administrator.
    actor = SimpleNamespace(id=uuid4(), role="user")
    role = SimpleNamespace(id=uuid4(), code="hr_manager", grant_version=1)

    async def get_role(*args, **kwargs):
        return role

    async def actor_roles(*args, **kwargs):
        return [role]

    monkeypatch.setattr(PagePermissionRepository, "get_role_for_update", get_role)
    monkeypatch.setattr(rbac_api, "resolve_user_roles", actor_roles)
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: actor
    app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            f"/api/v1/identity/admin/roles/{role.id}/page-permissions",
            json={
                "expected_grant_version": 1,
                "grants": [],
                "reason": "尝试调整本人角色",
            },
        )
        assert response.status_code == 403
        assert "本人所属角色" in response.json()["detail"]


@pytest.mark.asyncio
async def test_department_mapping_and_profile_cannot_self_escalate(monkeypatch):
    from app.platform.identity import api, rbac_api

    actor = SimpleNamespace(
        id=uuid4(),
        role="admin",
        department="采购部",
        feishu_department_ids='["own-department"]',
    )
    monkeypatch.setattr(
        PagePermissionService, "is_super_admin", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        api.PermissionGrantRepository,
        "get_user_for_update",
        AsyncMock(return_value=actor),
    )
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.include_router(api.user_router, prefix="/api/v1/identity")
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for target in (
            {"department_name": "采购部"},
            {"feishu_department_id": "own-department"},
        ):
            response = await client.post(
                "/api/v1/identity/admin/dept-rules",
                json={"role_id": str(uuid4()), **target},
            )
            assert response.status_code == 403
            assert "本人部门" in response.json()["detail"]
        response = await client.put(
            f"/api/v1/identity/users/{actor.id}", json={"department": "高权限部门"}
        )
        assert response.status_code == 403
        assert "授权关联部门" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("updates", "changed"),
    [
        ({"department": "质量部"}, True),
        ({"department": None}, True),
        ({"status": "disabled"}, True),
        ({"role": "admin"}, True),
        ({"department": "采购部"}, False),
        ({"name": "更新姓名"}, False),
    ],
)
async def test_user_context_changes_expire_authorization_snapshots(
    monkeypatch, updates, changed
):
    from app.platform.identity import api

    actor = SimpleNamespace(id=uuid4(), role="admin")
    user = SimpleNamespace(
        id=uuid4(),
        name="采购员",
        role="user",
        status="active",
        department="采购部",
        grant_version=7,
    )
    db = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
    outbox = AsyncMock()
    audit = AsyncMock()
    permissions_changed = AsyncMock()
    scope_changed = AsyncMock()
    monkeypatch.setattr(
        api.PermissionGrantRepository,
        "get_user_for_update",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(api.PermissionGrantRepository, "create_outbox_event", outbox)
    monkeypatch.setattr(api, "record_audit_log", audit)
    monkeypatch.setattr(api, "publish_permissions_changed", permissions_changed)
    monkeypatch.setattr(api, "publish_data_scope_changed", scope_changed)
    monkeypatch.setattr(api, "resolve_user_roles", AsyncMock(return_value=[]))
    app = FastAPI()
    app.include_router(api.user_router, prefix="/api/v1/identity")
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(f"/api/v1/identity/users/{user.id}", json=updates)
    assert response.status_code == 200
    assert user.grant_version == (8 if changed else 7)
    assert outbox.await_count == int(changed)
    assert audit.await_count == int(changed)
    assert db.commit.await_count == int(changed)
    if changed:
        assert outbox.call_args.kwargs["grant_version"] == 8
        assert outbox.call_args.kwargs["user_id"] == user.id
        permissions_changed.assert_awaited_once_with(user.id)
        scope_changed.assert_awaited_once_with("user", user.id)
    else:
        permissions_changed.assert_not_awaited()
        scope_changed.assert_not_awaited()


def test_production_summary_route_bound_to_overview_page():
    """生产汇总只读端点绑定到生产概览页（query 权限 + dashboard 适配）。"""
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/production/production-summary"
    )
    assert binding is not None
    assert binding.page_keys == ("production:overview",)
    assert binding.permission == "query"
    assert binding.scope_adapter == "production.dashboard"


def test_plans_get_route_covers_overview_and_sales_plan_pages():
    """/plans 读取同时授权产销计划页与生产概览页，写操作不受影响。"""
    binding = page_policy.api_binding_for_route("GET", "/api/v1/production/plans")
    assert binding is not None
    assert "production:overview" in binding.page_keys
    assert "production:plan:sales-plan" in binding.page_keys


def test_hr_feishu_apps_route_bound_to_settings_page():
    """/feishu-settings/apps 读取双应用配置，绑定到 HR 设置-飞书页并带数据范围。"""
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/hr/feishu-settings/apps"
    )
    assert binding is not None
    assert "hr:hr-settings:hr-settings-feishu" in binding.page_keys
    assert binding.permission == "query"
    assert binding.scope_adapter == "hr.settings"


def test_certificate_analyze_routes_bound_to_cal_external_page():
    """校准证书 AI 识别/重新匹配接口绑定到外部校准检定页（operate 权限）。"""
    for suffix in ("certificate-analyze", "certificate-rematch"):
        binding = page_policy.api_binding_for_route(
            "POST",
            f"/api/v1/quality/instruments/cal-external/{suffix}",
        )
        assert binding is not None, suffix
        assert (
            "quality:inspection:inspection-instruments:"
            "inspection-instruments-cal-external"
        ) in binding.page_keys
        assert binding.permission == "operate"
        assert binding.scope_adapter == "quality.reviewed_resource"


def test_browse_folder_route_removed_from_bindings():
    """遗留服务端弹窗接口 /email/browse-folder 已下线，不再有页面登记。"""
    assert (
        page_policy.api_binding_for_route(
            "POST", "/api/v1/hr/email/browse-folder"
        )
        is None
    )


def test_quality_shared_read_routes_cover_sibling_pages():
    """跨页共享的只读端点同时授权调用页，写操作保持属主页绑定。"""
    binding = page_policy.api_binding_for_route("GET", "/api/v1/quality/capas")
    assert binding is not None
    assert "quality:capas:capa-ledger" in binding.page_keys
    assert "quality:capas:capa-plans" in binding.page_keys
    write_binding = page_policy.api_binding_for_route(
        "POST", "/api/v1/quality/capas"
    )
    assert write_binding is not None
    assert write_binding.page_keys == ("quality:capas:capa-ledger",)

    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/quality/deviation-report-records"
    )
    assert binding is not None
    assert "quality:deviations:deviation-records" in binding.page_keys
    assert "quality:deviations:deviation-investigations" in binding.page_keys

    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/quality/feishu/validations"
    )
    assert binding is not None
    assert "quality:validation:validation-plans" in binding.page_keys
    for suffix in (
        "equipment-qualification",
        "process-validation",
        "cleaning-validation",
        "other-validations",
    ):
        assert f"quality:validation:{suffix}" in binding.page_keys
    delete_binding = page_policy.api_binding_for_route(
        "DELETE", "/api/v1/quality/feishu/validations/{record_id}"
    )
    assert delete_binding is not None
    assert delete_binding.page_keys == ("quality:validation:validation-plans",)


def test_quality_feishu_settings_read_covers_push_ledger_pages():
    """飞书应用配置读取授权四个业务推送页（响应仅含掩码密钥），写入仍仅设置页。"""
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/quality/feishu-settings/app"
    )
    assert binding is not None
    assert binding.permission == "query"
    assert set(binding.page_keys) == {
        "quality:quality-settings",
        "quality:deviations:deviation-records",
        "quality:deviations:deviation-investigations",
        "quality:oos-oot:oos-oot-report-records",
        "quality:oos-oot:oos-oot-investigation-push",
    }
    write_binding = page_policy.api_binding_for_route(
        "PUT", "/api/v1/quality/feishu-settings/app"
    )
    assert write_binding is not None
    assert write_binding.page_keys == ("quality:quality-settings",)


def test_quality_module_landing_routes_resolve_reviewed_alias():
    """变更控制与仪器管理目录页路由解析到评审别名页，仪表盘绑定包含别名页。"""
    assert (
        page_policy.page_key_for_route("/quality/change")
        == "quality:change:change-ledger"
    )
    assert (
        page_policy.page_key_for_route("/quality/inspection/instruments")
        == "quality:inspection:inspection-instruments:"
        "inspection-instruments-equipment"
    )
    # 子页面路由不受目录别名影响，仍按最长前缀解析到叶子页。
    assert (
        page_policy.page_key_for_route("/quality/change/ledger")
        == "quality:change:change-ledger"
    )
    assert (
        page_policy.page_key_for_route(
            "/quality/inspection/instruments/equipment"
        )
        == "quality:inspection:inspection-instruments:"
        "inspection-instruments-equipment"
    )
    dashboard = page_policy.api_binding_for_route(
        "GET", "/api/v1/quality/instruments/dashboard"
    )
    assert dashboard is not None
    assert (
        "quality:inspection:inspection-instruments:"
        "inspection-instruments-equipment"
    ) in dashboard.page_keys
    stats = page_policy.api_binding_for_route(
        "GET", "/api/v1/quality/statistics/changes"
    )
    assert stats is not None
    assert "quality:change:change-ledger" in stats.page_keys
