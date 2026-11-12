from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.api.router import api_router
from app.core.database import get_db
from app.core.exceptions import AppException
from app.main import app, app_exception_handler
from app.modules.safety.api.checks import SafetyService
from app.modules.safety.schemas import SafetyCheckResponse
from app.platform.identity import deps, page_policy
from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.rbac import _flatten_seed_menus
from app.platform.identity.safety_api_contract import SAFETY_SIGNATURE_ROUTES
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
async def test_safety_passes_the_integration_check(monkeypatch):
    menus = [
        ActiveMenuPage(
            key=node["key"],
            name=node["name"],
            route_path=node["path"],
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
    assert (
        await PagePermissionService().integration_gaps(None, module_code="safety") == []
    )


def test_signature_routes_keep_their_separate_protocol_boundary():
    mounted = {
        (method, route.path): route
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    for method, path in SAFETY_SIGNATURE_ROUTES:
        route = mounted[method, path]
        assert page_policy.api_binding_for_route(method, path) is None
        assert not any(
            getattr(dependency.call, "_dazah_module_code", None)
            for dependency in route.dependant.dependencies
        )
    routes = tuple(page_policy.collect_http_route_catalog(app.routes))
    catalog = page_policy.ApiRouteCatalog(
        (*routes, ("POST", "/api/v1/safety/sign-relay/"))
    )
    issues = page_policy.page_api_catalog_issues("safety", catalog=catalog).messages()
    assert len(issues) == 1
    assert "POST /api/v1/safety/sign-relay/" in issues[0]


@pytest.mark.asyncio
async def test_safety_review_requires_the_matching_grant_and_rejects_ambiguous_input(
    monkeypatch,
):
    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.add_exception_handler(AppException, app_exception_handler)
    db = SimpleNamespace(commit=AsyncMock())
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    grant = EffectivePageGrantOut(
        page_key="safety:training-check:safety-check",
        module_code="safety",
        permissions=["access", "query", "operate"],
        sensitive_actions=["approve"],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    check_id = uuid4()
    now = datetime.now(UTC)
    check = SafetyCheckResponse(
        id=check_id,
        check_no="CHECK-TEST",
        check_date=now,
        status="reviewed",
        created_at=now,
        updated_at=now,
        result="qualified",
    )
    review = AsyncMock(return_value=check)
    edit = AsyncMock(return_value=None)
    monkeypatch.setattr(SafetyService, "review_check", review)
    monkeypatch.setattr(SafetyService, "update_check", edit)
    path = f"/api/v1/safety/checks/{check_id}"
    headers = {"X-Dazah-Page-Path": "/safety/check"}
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{path}/review?result=unqualified", headers=headers
        )
        assert response.status_code == 403
        response = await client.post(
            f"{path}/review?result=qualified&result=unqualified", headers=headers
        )
        assert response.status_code == 422
        response = await client.put(path, json={"status": "reviewed"}, headers=headers)
        assert response.status_code == 403
        review.assert_not_awaited()
        edit.assert_not_awaited()

        response = await client.post(f"{path}/review?result=qualified", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "reviewed"
        assert response.json()["data"]["result"] == "qualified"
        review.assert_awaited_once_with(check_id, "qualified")
