"""Actual production routes must agree with page and decision grants."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.production import api, dr_schedule_api
from app.modules.production.repository import ProductionRepository
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


def acceptance_app(
    router, monkeypatch, page_key, actions=(), scope_type="all"
):
    app = FastAPI()
    app.include_router(
        router,
        prefix="/api/v1/production",
        dependencies=[Depends(deps.require_module_view("production"))],
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=Mock(fetchone=Mock(return_value=(uuid4(), "pending_approval")))
        ),
        commit=AsyncMock(),
    )
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user", name="权限验收用户"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=page_key,
        module_code="production",
        permissions=["access", "query", "operate"],
        sensitive_actions=list(actions),
        data_scope=PageDataScopeInput(scope_type=scope_type),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    return app, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_type,expected",
    [
        ("all", (True, True)),
        ("production_fermentation", (True, False)),
        ("production_extraction", (False, True)),
    ],
)
async def test_overview_uses_real_stage_scope_without_legacy_permission(
    monkeypatch, scope_type, expected
):
    from app.modules.production import fermentation_board_api
    from app.platform.identity import rbac

    app, _ = acceptance_app(
        fermentation_board_api.router, monkeypatch, "production:overview",
        scope_type=scope_type,
    )
    monkeypatch.setattr(rbac, "resolve_user_permissions", AsyncMock(return_value=[]))
    summary = AsyncMock(return_value={"visible": True})
    monkeypatch.setattr(
        fermentation_board_api.board, "build_production_summary", summary
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/production-summary",
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 200
    assert response.json()["data"] == {"visible": True}
    assert summary.await_args.kwargs["has_ferm"] is expected[0]
    assert summary.await_args.kwargs["has_extract"] is expected[1]


@pytest.mark.asyncio
async def test_extraction_scope_cannot_change_fermentation_actuals(monkeypatch):
    from app.modules.production import fermentation_board_api

    app, _ = acceptance_app(
        fermentation_board_api.router, monkeypatch, "production:overview",
        scope_type="production_extraction",
    )
    save = AsyncMock()
    monkeypatch.setattr(fermentation_board_api.board, "upsert_batch_actual", save)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/fermentation-batch-actuals",
            json={"batch_no": "FA26233", "yield_kg": 100},
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 403
    save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page_key", ["production:overview", "production:batches:workshop-201-3"]
)
async def test_remaining_production_pages_can_load_their_batch_selector(
    monkeypatch, page_key
):
    app, _ = acceptance_app(api.router, monkeypatch, page_key)
    listing = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(ProductionRepository, "get_batches", listing)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/batches", headers={"X-Dazah-Page-Key": page_key}
        )
    assert response.status_code == 200
    assert response.json()["data"] == []
    listing.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actions,approve,expected",
    [
        (["approve"], True, 200),
        (["approve"], False, 403),
        (["reject"], False, 200),
        (["reject"], True, 403),
        ([], True, 403),
    ],
)
async def test_receiving_decision_requires_its_own_action(
    monkeypatch, actions, approve, expected
):
    key = "production:batches:workshop-201-3"
    app, session = acceptance_app(dr_schedule_api.router, monkeypatch, key, actions)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/dr/schedule/tasks/ACCEPTANCE-BATCH/approve",
            json={"approve": approve},
            headers={"X-Dazah-Page-Key": key},
        )
    assert response.status_code == expected
    assert session.commit.await_count == (1 if expected == 200 else 0)
    if expected == 200:
        assert response.json()["data"]["approval_status"] == (
            "approved" if approve else "rejected"
        )
    else:
        session.execute.assert_not_awaited()
