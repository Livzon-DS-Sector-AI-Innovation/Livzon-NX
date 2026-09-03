from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import deps, page_policy, rbac_api
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


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

    assert expected_gap in preview.catalog_gaps


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
                "/hr/changed-route"
                if item.key == target.page_key
                else item.route_path
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
async def test_preview_keeps_registered_module_without_pages_visible(monkeypatch):
    _preview_facts(monkeypatch)

    preview = await PagePermissionService().rollout_preview(
        None, module_code="environment"
    )

    assert "未登记有效菜单页面" in preview.catalog_gaps


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
    assert before.catalog_gaps == after.catalog_gaps
    assert before.preview_hash != after.preview_hash


@pytest.mark.asyncio
async def test_preview_hash_tracks_live_menu_changes(monkeypatch):
    _preview_facts(monkeypatch)
    service = PagePermissionService()
    before = await service.rollout_preview(None, module_code="hr")
    catalog = await PagePermissionRepository().active_menu_page_catalog(None)
    changed = [
        ActiveMenuPage(
            key=item.key,
            name=(
                f"更新后的菜单名称-{index}"
                if item.root_key == "hr"
                else item.name
            ),
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
async def test_publish_rejects_preview_after_valid_policy_changes(monkeypatch):
    _preview_facts(monkeypatch)
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
    actor = SimpleNamespace(id=uuid4(), role="admin", status="active", is_deleted=False)
    db = SimpleNamespace(
        add=Mock(),
        commit=AsyncMock(),
        flush=AsyncMock(),
        execute=AsyncMock(),
        scalar=AsyncMock(return_value=actor),
    )
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/identity/admin/page-permissions/modules/procurement/publish",
            json={
                "expected_version": before.current_version,
                "preview_hash": before.preview_hash,
                "reason": "测试发布预览过期",
                "confirmed": True,
            },
        )
    assert response.status_code == 409
    assert "预览已过期" in response.json()["detail"]
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
