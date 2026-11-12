from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import deps, page_policy, rbac_api
from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.rbac import _flatten_seed_menus
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


def test_employee_filter_options_use_employee_page_query_grant() -> None:
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/hr/employees/filter-options"
    )
    assert binding is not None
    assert binding.page_keys == ("hr:employee-management:profile",)
    assert binding.permission == "query"
    assert binding.scope_adapter == "hr.employee_department"


def test_reviewed_modules_have_complete_runtime_page_api_bindings() -> None:
    from app.main import app

    assert app.routes
    reviewed = {
        "production", "registration", "hr", "quality", "warehouse", "procurement"
    }
    pages = [
        page for page in page_policy.PAGE_DEFINITIONS
        if page.module_code in reviewed
    ]
    assert len(pages) == 239
    for module_code in reviewed:
        assert page_policy.page_api_catalog_gaps(module_code) == []


@pytest.mark.asyncio
async def test_requested_modules_pass_full_integration_check(monkeypatch):
    from app.main import app

    assert app.routes
    menus = [
        ActiveMenuPage(
            key=node["key"], name=node["name"], route_path=node["path"],
            root_key=node["key"].split(":", 1)[0],
        )
        for node in _flatten_seed_menus(SEED_MENUS)
        if not node["children"] and not node["disabled"] and node["path"]
    ]
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(return_value=menus),
    )
    modules = ["hr", "quality", "registration", "warehouse", "production"]
    result = await PagePermissionService().integration_gaps_for_modules(
        None, module_codes=modules
    )
    assert result == dict.fromkeys(modules, [])


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/hr/employee-fill", "hr:employee-management:profile"),
        ("/quality/deviations/record-1/ai", "quality:deviations:deviation-ledger"),
        (
            "/registration/review/domestic-completed",
            "registration:project:declaration-progress:domestic-completed",
        ),
        ("/registration/review/new-sheet", None),
        ("/registration/validation-audit/task-1/extra", None),
        ("/registration/dossier-writer/record-1", "registration:dossier-writer"),
        ("/warehouse/raw-material", "warehouse:materials:raw-summary"),
        (
            "/production/batches/workshop/201-3/scheduling",
            "production:batches:workshop-201-3",
        ),
    ],
)
def test_reviewed_aliases_resolve_to_business_page_keys(path, expected):
    assert page_policy.page_key_for_route(path) == expected


def test_legacy_registration_review_links_preserve_sheet_scope():
    for page in page_policy.PAGES_BY_MODULE["registration"]:
        if page.route_path.startswith("/registration/declaration-progress/"):
            sheet = page.route_path.rsplit("/", 1)[1]
            assert page_policy.page_key_for_route(f"/registration/review/{sheet}") == (
                page.page_key
            )


def test_new_workshop_child_still_reports_an_integration_gap():
    route = "/production/batches/workshop/201-3/new-stage"
    gaps = page_policy.frontend_page_catalog_issues("production", [route]).messages()
    assert len(gaps) == 1
    assert route in gaps[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ["hidden", "duplicate", "risk_query", "write_query", "cross_module"]
)
async def test_broken_route_contract_is_denied_before_business_handler(
    monkeypatch, scenario
):
    method = "PUT" if scenario == "write_query" else "GET"
    path = "/api/v1/hr/employees/{employee_id}"
    binding = page_policy.PageApiBinding(
        route_path=path,
        method=method,
        page_keys=("hr:employee-management:profile",),
        permission="query",
        scope_adapter="hr.employee_department",
    )
    if scenario == "risk_query":
        binding = replace(binding, sensitive_action="delete")
    if scenario == "cross_module":
        binding = replace(binding, page_keys=("purchasing:supplier",))
    monkeypatch.setattr(
        page_policy, "PAGE_API_BINDINGS", () if scenario == "hidden" else (binding,)
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="enforced")),
    )
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[
                EffectivePageGrantOut(
                    page_key="hr:employee-management:profile",
                    module_code="hr",
                    permissions=["access", "query", "operate"],
                    sensitive_actions=["delete"],
                    data_scope=PageDataScopeInput(scope_type="all"),
                    source="user",
                ),
            ]
        ),
    )
    app = FastAPI()
    called = Mock()

    async def endpoint(employee_id: str):
        called()
        return {"id": employee_id}

    for _ in range(2 if scenario == "duplicate" else 1):
        app.add_api_route(
            path,
            endpoint,
            methods=[method],
            include_in_schema=False,
            dependencies=[Depends(deps.require_module_view("hr"))],
        )
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4()
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/hr/employees/one",
            headers={"X-Dazah-Page-Key": "hr:employee-management:profile"},
        )
    assert response.status_code == 403
    called.assert_not_called()


def _preview_facts(monkeypatch):
    monkeypatch.setattr(
        "app.platform.identity.page_permissions.load_frontend_page_routes", lambda: []
    )
    monkeypatch.setattr(
        PagePermissionRepository, "get_rollout", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        PagePermissionRepository, "list_active_users", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_page_keys",
        AsyncMock(return_value=set(page_policy.PAGES_BY_KEY)),
    )
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(
            return_value=[
                ActiveMenuPage(
                    key=page.page_key,
                    name=page.page_name,
                    route_path=page.route_path,
                    root_key=page.page_key.split(":", 1)[0],
                )
                for page in page_policy.PAGE_DEFINITIONS
            ]
        ),
    )
    monkeypatch.setattr(page_policy, "_tool_catalog_provider", lambda: [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entry", "expected_gap"),
    [
        (
            ActiveMenuPage(
                key=None,
                name="新增员工页面",
                route_path="/hr/new-employee-page",
                root_key="hr",
            ),
            "菜单页面缺少稳定权限标识：新增员工页面（/hr/new-employee-page）",
        ),
        (
            ActiveMenuPage(
                key="hr:new-employee-page",
                name="新增员工页面",
                route_path="/hr/new-employee-page",
                root_key="hr",
            ),
            "新增菜单页面尚未接入权限登记：新增员工页面（hr:new-employee-page）",
        ),
    ],
)
async def test_preview_blocks_active_menu_without_permission_registration(
    monkeypatch, entry, expected_gap
):
    _preview_facts(monkeypatch)
    catalog = await PagePermissionRepository().active_menu_page_catalog(None)
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(return_value=[*catalog, entry]),
    )

    preview = await PagePermissionService().rollout_preview(None, module_code="hr")

    assert any(
        entry.route_path in gap and expected_gap.split("：", 1)[0] in gap
        for gap in preview.catalog_gaps
    )


@pytest.mark.asyncio
async def test_preview_detects_registered_page_route_mismatch(monkeypatch):
    _preview_facts(monkeypatch)
    catalog = await PagePermissionRepository().active_menu_page_catalog(None)
    target = page_policy.PAGES_BY_MODULE["hr"][0]
    changed = [
        ActiveMenuPage(
            key=item.key,
            name=item.name,
            route_path=(
                "/hr/changed-route" if item.key == target.page_key else item.route_path
            ),
            root_key=item.root_key,
        )
        for item in catalog
    ]
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(return_value=changed),
    )

    preview = await PagePermissionService().rollout_preview(None, module_code="hr")

    assert any("菜单页面路由与权限登记不一致" in gap for gap in preview.catalog_gaps)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current_key", "legacy_key"),
    [
        (
            "warehouse:hardware:hardware-hardware-101-1-workshop",
            "warehouse:hardware:hardware-101-1-workshop",
        ),
        (
            "warehouse:product-inventory:product-details:product-detail-l-phenylalanine",
            "warehouse:product:product-details:product-detail-l-phenylalanine",
        ),
    ],
)
async def test_preview_accepts_legacy_warehouse_menu_keys(
    monkeypatch, current_key, legacy_key
):
    _preview_facts(monkeypatch)
    catalog = await PagePermissionRepository().active_menu_page_catalog(None)
    changed = [
        ActiveMenuPage(
            key=legacy_key if item.key == current_key else item.key,
            name=item.name,
            route_path=item.route_path,
            root_key=item.root_key,
        )
        for item in catalog
    ]
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(return_value=changed),
    )

    preview = await PagePermissionService().rollout_preview(
        None, module_code="warehouse"
    )

    assert not any(legacy_key in gap for gap in preview.catalog_gaps)


@pytest.mark.asyncio
async def test_preview_keeps_registered_module_without_pages_visible(monkeypatch):
    _preview_facts(monkeypatch)

    preview = await PagePermissionService().rollout_preview(
        None, module_code="environment"
    )

    assert any("未登记有效菜单页面" in gap for gap in preview.catalog_gaps)


@pytest.mark.asyncio
async def test_preview_hash_tracks_actual_route_changes_even_with_same_gap_counts(
    monkeypatch,
):
    _preview_facts(monkeypatch)
    service = PagePermissionService()
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [("GET", "/api/v1/hr/unreviewed-a")],
    )
    before = await service.rollout_preview(None, module_code="hr")
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [("GET", "/api/v1/hr/unreviewed-b")],
    )
    after = await service.rollout_preview(None, module_code="hr")
    assert len(before.catalog_gaps) == len(after.catalog_gaps)
    assert before.catalog_gaps != after.catalog_gaps
    assert before.preview_hash != after.preview_hash


@pytest.mark.asyncio
async def test_preview_reuses_catalog_for_gaps_and_hash(monkeypatch):
    _preview_facts(monkeypatch)
    menus = PagePermissionRepository.active_menu_page_catalog
    routes = [(item.method, item.route_path) for item in page_policy.PAGE_API_BINDINGS]
    apis = Mock(side_effect=lambda: list(routes))
    tools = Mock(return_value=[])
    monkeypatch.setattr(page_policy, "_api_catalog_provider", apis)
    monkeypatch.setattr(page_policy, "_tool_catalog_provider", tools)
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: SimpleNamespace(
        role="admin"
    )
    app.dependency_overrides[get_db] = lambda: None
    url = "/api/v1/identity/admin/page-permissions/modules/hr/preview"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get(url)
        assert first.status_code == 200
        first_data = first.json()["data"]
        assert first_data["catalog_gaps"] == []
        assert all(mock.call_count == 1 for mock in (menus, apis, tools))
        routes.append(("GET", "/api/v1/hr/new-preview-check"))
        second = await client.get(url)
        assert second.status_code == 200
        second_data = second.json()["data"]
        assert len(second_data["catalog_gaps"]) == 1
        assert first_data["preview_hash"] != second_data["preview_hash"]
        assert all(mock.call_count == 2 for mock in (menus, apis, tools))


@pytest.mark.asyncio
async def test_preview_hash_tracks_live_menu_changes(monkeypatch):
    _preview_facts(monkeypatch)
    service = PagePermissionService()
    before = await service.rollout_preview(None, module_code="hr")
    catalog = await PagePermissionRepository().active_menu_page_catalog(None)
    changed = [
        ActiveMenuPage(
            key=item.key,
            name=(f"更新后的菜单名称-{index}" if item.root_key == "hr" else item.name),
            route_path=item.route_path,
            root_key=item.root_key,
        )
        for index, item in enumerate(catalog)
    ]
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(return_value=changed),
    )

    after = await service.rollout_preview(None, module_code="hr")

    assert before.catalog_gaps == after.catalog_gaps
    assert before.preview_hash != after.preview_hash


@pytest.mark.asyncio
async def test_integration_check_recomputes_after_policy_changes(monkeypatch):
    _preview_facts(monkeypatch)
    actual_routes = [
        (item.method, item.route_path) for item in page_policy.PAGE_API_BINDINGS
    ]
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: actual_routes,
    )
    service = PagePermissionService()
    before = await service.rollout_preview(None, module_code="procurement")
    assert not before.catalog_gaps
    # Still valid, but the reviewed scope-adapter contract changed since preview.
    bindings = tuple(
        replace(item, scope_adapter="procurement.reviewed_supplier_adapter_v2")
        if item.route_path == "/api/v1/procurement/suppliers"
        else item
        for item in page_policy.PAGE_API_BINDINGS
    )
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", bindings)
    after = await service.rollout_preview(None, module_code="procurement")
    assert not after.catalog_gaps
    assert before.preview_hash != after.preview_hash
    assert await service.integration_gaps(None, module_code="procurement") == []
    assert not after.catalog_gaps
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", bindings[1:])
    assert await service.integration_gaps(None, module_code="procurement")


@pytest.mark.asyncio
async def test_module_integration_api_returns_current_gaps(monkeypatch):
    gaps = ["接口绑定缺失"]
    service = SimpleNamespace(
        integration_gaps_for_modules=AsyncMock(
            side_effect=lambda db, module_codes: {
                code: gaps if code == "hr" else [] for code in module_codes
            }
        )
    )
    monkeypatch.setattr(rbac_api, "PagePermissionService", lambda: service)
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: SimpleNamespace(
        role="admin"
    )
    app.dependency_overrides[get_db] = lambda: None
    url = "/api/v1/identity/admin/page-permissions/modules"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get(url)
        assert first.status_code == 200, first.text
        hr = next(item for item in first.json()["data"] if item["module_code"] == "hr")
        assert hr == {"module_code": "hr", "passed": False, "catalog_gaps": gaps}
        gaps.clear()
        second = await client.get(url)
        assert second.status_code == 200, second.text
        hr = next(item for item in second.json()["data"] if item["module_code"] == "hr")
        assert hr["passed"] is True
        assert hr["catalog_gaps"] == []
        assert (await client.post(url + "/hr/publish", json={})).status_code == 404
