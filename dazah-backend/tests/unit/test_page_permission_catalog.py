from dataclasses import replace

import pytest
from fastapi import FastAPI

from app.platform.identity import page_policy


def test_procurement_catalog_covers_actual_endpoints_and_valid_menu_pages():
    assert page_policy.page_api_catalog_gaps("procurement") == []


def test_new_endpoint_without_a_page_contract_blocks_publication(monkeypatch):
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [("POST", "/api/v1/procurement/unregistered")],
    )
    assert any(
        "1 个业务接口" in gap
        for gap in page_policy.page_api_catalog_gaps("procurement")
    )


def test_frontend_catalog_contains_new_categories_but_not_directory_grants():
    assert (
        page_policy.page_key_for_route("/purchasing/request/urgent")
        in page_policy.PAGES_BY_KEY
    )
    assert (
        page_policy.page_key_for_route("/purchasing/settings")
        in page_policy.PAGES_BY_KEY
    )
    assert "purchasing" not in page_policy.PAGES_BY_KEY
    assert "hr" not in page_policy.PAGES_BY_KEY


def test_real_catalog_includes_hidden_duplicate_and_mounted_http_routes():
    app = FastAPI()
    app.add_api_route("/api/v1/hr/hidden", lambda: None, include_in_schema=False)
    app.add_api_route("/api/v1/hr/hidden", lambda: None, include_in_schema=False)
    child = FastAPI()
    child.add_api_route("/events", lambda: None, methods=["POST"])
    app.mount("/api/v1/hr/sub", child)
    actual = page_policy.collect_http_route_catalog(app.routes)
    assert actual.count(("GET", "/api/v1/hr/hidden")) == 2
    assert ("POST", "/api/v1/hr/sub/events") in actual


def test_main_catalog_does_not_depend_on_cached_openapi(monkeypatch):
    from app import main

    app = FastAPI()
    app.openapi()
    app.add_api_route("/api/v1/hr/hidden", lambda: None, include_in_schema=False)
    monkeypatch.setattr(main, "app", app)
    assert ("GET", "/api/v1/hr/hidden") in main._page_permission_api_catalog()


@pytest.mark.parametrize(
    "patch",
    [
        {"permission": "unknown"},
        {"page_keys": ()},
        {"page_keys": ("hr:employee-management:profile",)},
        {"page_keys": ("purchasing:supplier", "purchasing:supplier")},
        {"scope_adapter": " "},
        {"sensitive_action": "bulk_import", "permission": "query"},
        {"method": "DELETE", "permission": "query", "sensitive_action": "delete"},
        {"method": "DELETE", "permission": "operate", "sensitive_action": None},
    ],
)
def test_invalid_binding_fails_at_lookup_and_publication(monkeypatch, patch):
    original = page_policy.PageApiBinding(
        route_path="/api/v1/procurement/suppliers/import",
        method="POST",
        page_keys=("purchasing:supplier",),
        permission="operate",
        sensitive_action="bulk_import",
        scope_adapter="not_applicable",
    )
    broken = replace(original, **patch)
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", (broken,))
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [(broken.method, broken.route_path)],
    )
    assert page_policy.api_binding_for_route(broken.method, broken.route_path) is None
    assert any(
        "接口策略无效" in gap
        for gap in page_policy.page_api_catalog_gaps("procurement")
    )


def test_duplicate_actual_routes_and_orphaned_policy_block_publication(monkeypatch):
    binding = page_policy.PageApiBinding(
        route_path="/api/v1/hr/employees",
        method="GET",
        page_keys=("hr:employee-management:profile",),
        permission="query",
        scope_adapter="hr.employee_department",
    )
    monkeypatch.setattr(page_policy, "PAGE_API_BINDINGS", (binding,))
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [
            ("GET", binding.route_path),
            ("GET", binding.route_path),
        ],
    )
    assert any("重复" in gap for gap in page_policy.page_api_catalog_gaps("hr"))
    monkeypatch.setattr(page_policy, "_api_catalog_provider", lambda: [])
    assert any("不存在" in gap for gap in page_policy.page_api_catalog_gaps("hr"))
