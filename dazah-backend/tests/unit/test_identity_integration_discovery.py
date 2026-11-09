import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import (
    page_permissions,
    page_policy,
    page_route_catalog,
    rbac_api,
)
from app.platform.identity.integration_gaps import IntegrationGaps
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.schemas import PermissionModuleIntegrationOut


def test_gap_count_uses_object_identity_and_preserves_all_reasons():
    gaps = IntegrationGaps()
    gaps.add("接口", "GET /one", "GET /one", "权限无效")
    gaps.add("接口", "GET /one", "GET /one", "范围无效")
    gaps.add("接口", "GET /one", "GET /one", "权限无效")
    gaps.add("接口", "GET /two", "GET /two", "权限无效")
    assert len(gaps.messages()) == 2
    assert "权限无效" in gaps.messages()[0]
    assert "范围无效" in gaps.messages()[0]


@pytest.mark.parametrize("count", [1, 2, 10])
def test_each_unregistered_method_and_path_is_counted(monkeypatch, count):
    baseline = [
        (item.method, item.route_path) for item in page_policy.PAGE_API_BINDINGS
    ]
    new = [("GET", f"/api/v1/procurement/new-{index}") for index in range(count)]
    monkeypatch.setattr(page_policy, "_api_catalog_provider", lambda: baseline + new)
    gaps = page_policy.page_api_catalog_gaps("procurement")
    assert len(gaps) == count
    assert all(any(f"{method} {path}" in gap for gap in gaps) for method, path in new)


def test_duplicate_invalid_binding_is_one_interface_gap_with_all_reasons(monkeypatch):
    baseline = [
        (item.method, item.route_path) for item in page_policy.PAGE_API_BINDINGS
    ]
    target = page_policy.api_bindings_for_module("hr")[0]
    broken = replace(target, scope_adapter=" ", permission="unknown")
    monkeypatch.setattr(
        page_policy,
        "PAGE_API_BINDINGS",
        tuple(
            broken if item is target else item for item in page_policy.PAGE_API_BINDINGS
        ),
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: [*baseline, (target.method, target.route_path)],
    )
    gaps = page_policy.page_api_catalog_gaps("hr")
    assert len(gaps) == 1
    assert target.route_path in gaps[0]
    assert all(reason in gaps[0] for reason in ("重复", "主权限无效", "数据范围适配"))


def page(root: Path, relative: str) -> None:
    target = root / relative / "page.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "export default function Page() { return null }", encoding="utf-8"
    )


def test_scanner_handles_route_groups_dynamic_slots_private_and_intercepted_pages(
    tmp_path,
):
    for relative in (
        "(dashboard)/hr/profile",
        "(dashboard)/hr/[id]",
        "(dashboard)/hr/_private/leak",
        "(dashboard)/hr/@detail/profile",
        "(dashboard)/hr/@modal/(.)profile",
        "(dashboard)/hr/profile/(..)other",
        "(dashboard)/hr/%5Fpublic",
    ):
        page(tmp_path, relative)
    assert page_route_catalog.collect_frontend_page_routes(tmp_path) == [
        "/hr/[id]",
        "/hr/_public",
        "/hr/other",
        "/hr/profile",
    ]


def test_live_source_discovery_does_not_cache_new_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(page_route_catalog, "SOURCE_ROOTS", (tmp_path,))
    page(tmp_path, "(dashboard)/energy")
    assert page_route_catalog.load_frontend_page_routes() == ["/energy"]
    page(tmp_path, "(dashboard)/energy/new-analysis")
    routes = page_route_catalog.load_frontend_page_routes()
    gaps = page_policy.frontend_page_catalog_issues("energy", routes).messages()
    assert len(gaps) == 1
    assert "/energy/new-analysis" in gaps[0]


def test_dynamic_routes_recognize_catalog_pages_without_trusting_new_children():
    gaps = page_policy.frontend_page_catalog_issues(
        "procurement",
        ["/purchasing/request/[category]", "/purchasing/request/new/analysis"],
    ).messages()
    assert len(gaps) == 1
    assert "/purchasing/request/new/analysis" in gaps[0]
    gaps = page_policy.frontend_page_catalog_issues(
        "registration", ["/registration/review/unregistered-analysis"]
    ).messages()
    assert len(gaps) == 1
    gaps = page_policy.frontend_page_catalog_issues(
        "procurement",
        ["/purchasing/[...unregistered]", "/purchasing/request/[unreviewed]"],
    ).messages()
    assert len(gaps) == 2


def test_empty_live_directory_cannot_produce_a_passing_check(tmp_path, monkeypatch):
    monkeypatch.setattr(page_route_catalog, "SOURCE_ROOTS", (tmp_path,))
    with pytest.raises(page_route_catalog.PageRouteCatalogError):
        page_route_catalog.load_frontend_page_routes()


def test_snapshot_is_used_without_source_and_bad_inventory_fails_closed(
    tmp_path, monkeypatch
):
    target = tmp_path / "routes.json"
    monkeypatch.setattr(page_route_catalog, "SOURCE_ROOTS", ())
    monkeypatch.setattr(page_route_catalog, "CATALOG_PATH", target)
    target.write_text(
        json.dumps({"version": 1, "routes": ["/energy/new"]}), encoding="utf-8"
    )
    assert page_route_catalog.load_frontend_page_routes() == ["/energy/new"]
    for content in ('{"version": 2}', '{"version": 1, "routes": []}', "invalid"):
        target.write_text(content, encoding="utf-8")
        with pytest.raises(page_route_catalog.PageRouteCatalogError):
            page_route_catalog.load_frontend_page_routes()
    target.unlink()
    with pytest.raises(page_route_catalog.PageRouteCatalogError):
        page_route_catalog.load_frontend_page_routes()


def test_deployment_snapshot_matches_current_frontend_sources():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/generate-page-routes.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_generator_updates_inventory_and_rejects_a_stale_snapshot(
    tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "generate_page_routes", root / "scripts/generate-page-routes.py"
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    source = tmp_path / "dazah-frontend/src/app"
    target = tmp_path / "page_route_catalog.json"
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "CATALOG_PATH", target)
    monkeypatch.setattr(sys, "argv", ["generate-page-routes.py"])
    page(source, "(dashboard)/hr/report")
    assert generator.main() == 0
    monkeypatch.setattr(sys, "argv", ["generate-page-routes.py", "--check"])
    assert generator.main() == 0
    page(source, "(dashboard)/hr/second-report")
    assert generator.main() == 1
    assert json.loads(target.read_text(encoding="utf-8"))["routes"] == ["/hr/report"]


def setup_catalog(monkeypatch, source):
    monkeypatch.setattr(page_route_catalog, "SOURCE_ROOTS", (source,))
    monkeypatch.setattr(
        PagePermissionRepository,
        "active_menu_page_catalog",
        AsyncMock(
            return_value=[
                ActiveMenuPage(
                    key=item.page_key,
                    name=item.page_name,
                    route_path=item.route_path,
                    root_key=item.page_key.split(":", 1)[0],
                )
                for item in page_policy.PAGE_DEFINITIONS
            ]
        ),
    )
    monkeypatch.setattr(page_policy, "_tool_catalog_provider", lambda: [])
    baseline = [
        (item.method, item.route_path) for item in page_policy.PAGE_API_BINDINGS
    ]
    catalog_app = FastAPI()
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: baseline + page_policy.collect_http_route_catalog(catalog_app.routes),
    )
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: SimpleNamespace(
        role="admin"
    )
    app.dependency_overrides[get_db] = lambda: None
    return app, catalog_app


@pytest.mark.asyncio
async def test_real_module_api_discovers_new_hidden_interfaces_and_pages(
    tmp_path, monkeypatch
):
    app, catalog = setup_catalog(monkeypatch, tmp_path)
    catalog.add_api_route(
        "/api/v1/hr/unregistered",
        lambda: None,
        methods=["GET", "POST"],
        include_in_schema=False,
    )
    page(tmp_path, "(dashboard)/hr/new-report")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def check(expected):
            response = await client.get(
                "/api/v1/identity/admin/page-permissions/modules"
            )
            assert response.status_code == 200
            rows = [
                PermissionModuleIntegrationOut.model_validate(row)
                for row in response.json()["data"]
            ]
            hr = next(row for row in rows if row.module_code == "hr")
            assert hr.passed is False
            assert len(hr.catalog_gaps) == expected
            return hr.catalog_gaps

        gaps = await check(3)
        assert any("GET /api/v1/hr/unregistered" in gap for gap in gaps)
        assert any("POST /api/v1/hr/unregistered" in gap for gap in gaps)
        assert any("/hr/new-report" in gap for gap in gaps)
        page(tmp_path, "(dashboard)/hr/second-report")
        await check(4)
        (tmp_path / "(dashboard)/hr/second-report/page.tsx").unlink()
        await check(3)


@pytest.mark.asyncio
async def test_module_api_reports_unavailable_page_inventory_without_500(
    tmp_path, monkeypatch
):
    app, _ = setup_catalog(monkeypatch, tmp_path)

    def unavailable():
        raise page_route_catalog.PageRouteCatalogError("unavailable")

    monkeypatch.setattr(
        "app.platform.identity.page_permissions.load_frontend_page_routes", unavailable
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/identity/admin/page-permissions/modules")
    assert response.status_code == 200
    hr = next(row for row in response.json()["data"] if row["module_code"] == "hr")
    assert hr["passed"] is False
    assert any("检查目录｜前端页面目录" in gap for gap in hr["catalog_gaps"])


@pytest.mark.asyncio
async def test_module_check_reads_each_catalog_once_per_request(tmp_path, monkeypatch):
    app, catalog = setup_catalog(monkeypatch, tmp_path)
    page(tmp_path, "(dashboard)/hr")
    scans = Mock(wraps=page_permissions.load_frontend_page_routes)
    apis = Mock(wraps=page_policy._api_catalog_provider)
    tools = Mock(wraps=page_policy._tool_catalog_provider)
    monkeypatch.setattr(page_permissions, "load_frontend_page_routes", scans)
    monkeypatch.setattr(page_policy, "_api_catalog_provider", apis)
    monkeypatch.setattr(page_policy, "_tool_catalog_provider", tools)
    menus = PagePermissionRepository.active_menu_page_catalog
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/identity/admin/page-permissions/modules")
        assert response.status_code == 200
        before = response.json()["data"]
        assert all(mock.call_count == 1 for mock in (scans, apis, tools, menus))
        catalog.add_api_route("/api/v1/hr/new-fast-check", lambda: None)
        page(tmp_path, "(dashboard)/hr/new-fast-page")
        response = await client.get("/api/v1/identity/admin/page-permissions/modules")
        assert response.status_code == 200
        after = response.json()["data"]
        assert all(mock.call_count == 2 for mock in (scans, apis, tools, menus))
    old_hr = next(row for row in before if row["module_code"] == "hr")
    new_hr = next(row for row in after if row["module_code"] == "hr")
    assert len(new_hr["catalog_gaps"]) == len(old_hr["catalog_gaps"]) + 2
    assert new_hr["passed"] is False
    assert any("GET /api/v1/hr/new-fast-check" in gap for gap in new_hr["catalog_gaps"])
    assert any("/hr/new-fast-page" in gap for gap in new_hr["catalog_gaps"])
