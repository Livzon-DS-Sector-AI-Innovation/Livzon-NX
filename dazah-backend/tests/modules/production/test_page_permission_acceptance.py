"""Actual production routes must agree with page and decision grants."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.production import api, dr_schedule_api
from app.modules.production.repository import ProductionRepository
from app.modules.production.service import ProductionService
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize("product", ["MC", "LN", "DR", "FA", "LV", "MV", "TY"])
@pytest.mark.parametrize("restricted", [False, True])
async def test_scheduling_visible_product_list(monkeypatch, product, restricted):
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        visible_sections=[product] if restricted else None,
    )
    listing = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(schedule.schedule_excel_service, "list_archives", listing)
    monkeypatch.setattr(
        schedule.schedule_excel_service,
        "list_history_fixes",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        schedule.schedule_excel_service,
        "count_history_fixes",
        AsyncMock(return_value=0),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/schedule-excel",
            params={"product": product},
            headers={"X-Dazah-Page-Key": "production:plan:scheduling"},
        )
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert listing.await_args.kwargs["product_code"] == product


@pytest.mark.asyncio
@pytest.mark.parametrize("sections", [["MC"], []])
@pytest.mark.parametrize(
    "operation", ["list", "upload", "detail", "download", "delete"]
)
async def test_scheduling_hidden_product_cannot_access_archives(
    monkeypatch, sections, operation
):
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        actions=["delete", "bulk_import", "sensitive_export"],
        visible_sections=sections,
    )
    archive = SimpleNamespace(product_code="LN")
    listing = AsyncMock()
    deleting = AsyncMock()
    parsing = Mock()
    serialization = Mock()
    file_path = Mock()
    monkeypatch.setattr(
        schedule.schedule_excel_service, "get_archive", AsyncMock(return_value=archive)
    )
    monkeypatch.setattr(schedule.schedule_excel_service, "list_archives", listing)
    monkeypatch.setattr(schedule.schedule_excel_service, "delete_archive", deleting)
    monkeypatch.setattr(
        schedule.schedule_excel_service, "parse_workbook_bytes", parsing
    )
    monkeypatch.setattr(
        schedule.schedule_excel_service, "serialize_archive", serialization
    )
    monkeypatch.setattr(schedule, "_ensure_archive_file", file_path)
    headers = {"X-Dazah-Page-Key": "production:plan:scheduling"}
    path = f"/api/v1/production/schedule-excel/{uuid4()}"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if operation == "list":
            response = await client.get(
                "/api/v1/production/schedule-excel?product=LN", headers=headers
            )
        elif operation == "upload":
            response = await client.post(
                "/api/v1/production/schedule-excel?product=LN",
                headers=headers,
                files={
                    "file": (
                        "plan.xlsx",
                        b"unused",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        elif operation == "delete":
            response = await client.delete(path, headers=headers)
        else:
            # Query parameters cannot override the product persisted on the archive.
            response = await client.get(
                path + ("/file" if operation == "download" else "") + "?product=MC",
                headers=headers,
            )
    assert response.status_code == 403
    assert "该产品" in response.json()["detail"]
    listing.assert_not_awaited()
    deleting.assert_not_awaited()
    parsing.assert_not_called()
    serialization.assert_not_called()
    file_path.assert_not_called()


def acceptance_app(
    router, monkeypatch, page_key, actions=(), scope_type="all", visible_sections=None
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
        visible_sections=visible_sections,
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
async def test_overview_summary_removes_hidden_product_data(monkeypatch):
    from app.modules.production import fermentation_board_api

    app, _ = acceptance_app(
        fermentation_board_api.router, monkeypatch, "production:overview",
        visible_sections=["MC"],
    )
    summary = AsyncMock(return_value={"period": None, "rows": [
        {"product_code": "MC", "product_name": "霉酚酸", "alerts": []},
        {"product_code": "FA", "product_name": "L-苯丙氨酸", "alerts": ["secret"]},
    ]})
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
    assert [row["product_code"] for row in response.json()["data"]["rows"]] == ["MC"]


@pytest.mark.asyncio
async def test_overview_rejects_hidden_product_and_sales_plan_requests(monkeypatch):
    from app.modules.production import fermentation_board_api

    app, _ = acceptance_app(
        fermentation_board_api.router, monkeypatch, "production:overview",
        visible_sections=["MC"],
    )
    loader = AsyncMock()
    monkeypatch.setattr(fermentation_board_api.board, "load_archive_covering", loader)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/fermentation-board?product=FA",
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 403
    loader.assert_not_awaited()

    app, _ = acceptance_app(
        api.router, monkeypatch, "production:overview", visible_sections=["MC"]
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/sales-plan-details?month=2026-09",
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overview_line_status_omits_hidden_products(monkeypatch):
    from app.modules.production import fermentation_board_api

    app, _ = acceptance_app(
        fermentation_board_api.router, monkeypatch, "production:overview",
        visible_sections=["MC"],
    )
    monkeypatch.setattr(
        fermentation_board_api.board, "get_line_halted_map",
        AsyncMock(return_value={"MC": True, "FA": True}),
    )
    monkeypatch.setattr(
        fermentation_board_api.board, "latest_line_halt_events",
        AsyncMock(return_value={}),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/production-line-status",
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["halted"] == ["MC"]


@pytest.mark.asyncio
async def test_overview_plan_list_requires_an_allowed_product(monkeypatch):
    app, _ = acceptance_app(
        api.router, monkeypatch, "production:overview", visible_sections=["MC"]
    )
    plans = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(ProductionService, "get_plans", plans)
    headers = {"X-Dazah-Page-Key": "production:overview"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        allowed = await client.get(
            "/api/v1/production/plans?product_name=霉酚酸", headers=headers
        )
        denied = await client.get(
            "/api/v1/production/plans?product_name=L-苯丙氨酸", headers=headers
        )
        unfiltered = await client.get("/api/v1/production/plans", headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["data"] == []
    assert denied.status_code == 403
    assert unfiltered.status_code == 403
    plans.assert_awaited_once()


@pytest.mark.asyncio
async def test_shared_batch_route_rejects_hidden_product_context(monkeypatch):
    app, _ = acceptance_app(
        api.router, monkeypatch, "production:overview", visible_sections=["MC"]
    )
    listing = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(ProductionRepository, "get_batches", listing)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/production/batches?product_code=FA",
            headers={"X-Dazah-Page-Key": "production:overview"},
        )
    assert response.status_code == 403
    listing.assert_not_awaited()


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
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/production/tank-maintenance", None),
        (
            "POST",
            "/api/v1/production/tank-maintenance",
            {"tank_no": "302A", "reason": "检修"},
        ),
        (
            "DELETE",
            f"/api/v1/production/tank-maintenance/{uuid4()}",
            None,
        ),
        (
            "DELETE",
            f"/api/v1/production/fermentation-batch-actuals/{uuid4()}",
            None,
        ),
        (
            "POST",
            "/api/v1/production/fermentation-month-capacity",
            {"planned_capacity_kg": 1000},
        ),
    ],
)
async def test_extraction_scope_rejects_fermentation_only_operations(
    monkeypatch, method, path, body
):
    from app.modules.production import fermentation_board_api

    app, _ = acceptance_app(
        fermentation_board_api.router,
        monkeypatch,
        "production:overview",
        scope_type="production_extraction",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            path,
            json=body,
            headers={"X-Dazah-Page-Key": "production:overview"},
        )

    assert response.status_code == 403


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


@pytest.mark.asyncio
@pytest.mark.parametrize("sections", [["MC"], []])
@pytest.mark.parametrize(
    "operation", ["validate", "get-constraints", "save-constraints"]
)
async def test_scheduling_hidden_product_cannot_validate_or_configure(
    monkeypatch, sections, operation
):
    """排产校验与约束配置沿用排产页的产品可见性：未授权产品一律 403。"""
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        actions=["sync_config"],
        visible_sections=sections,
    )
    archive = SimpleNamespace(product_code="LN", rows=[])
    get_archive = AsyncMock(return_value=archive)
    building = AsyncMock()
    get_constraints = AsyncMock()
    upsert = AsyncMock()
    monkeypatch.setattr(schedule.schedule_excel_service, "get_archive", get_archive)
    monkeypatch.setattr(
        schedule.schedule_validation_service, "build_validation_report", building
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service,
        "get_constraint_setting",
        get_constraints,
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service,
        "upsert_constraint_setting",
        upsert,
    )
    headers = {"X-Dazah-Page-Key": "production:plan:scheduling"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if operation == "validate":
            response = await client.get(
                f"/api/v1/production/schedule-excel/{uuid4()}/validation",
                headers=headers,
            )
        elif operation == "get-constraints":
            response = await client.get(
                "/api/v1/production/schedule-constraints",
                params={"product": "LN"},
                headers=headers,
            )
        else:
            response = await client.post(
                "/api/v1/production/schedule-constraints",
                params={"product": "LN"},
                json={},
                headers=headers,
            )
    assert response.status_code == 403
    assert "该产品" in response.json()["detail"]
    building.assert_not_awaited()
    get_constraints.assert_not_awaited()
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_validation_and_constraints_allowed_for_visible_product(
    monkeypatch,
):
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        actions=["sync_config"],
        visible_sections=["FA"],
    )
    archive = SimpleNamespace(
        id=uuid4(), product_code="FA", rows=[], created_at="2026-09-30T10:00:00"
    )
    report = {"issues": [], "summary": {"warn": 0, "info": 0}}
    building = AsyncMock(return_value=report)
    get_constraints = AsyncMock(return_value=None)
    saved = SimpleNamespace(
        product_code="FA",
        standard_cycle_hours=61.0,
        cycle_tolerance_hours=4.0,
        max_cycle_hours=72.0,
        turnaround_hours=8.0,
        monthly_dump_target=26,
    )
    upsert = AsyncMock(return_value=saved)
    monkeypatch.setattr(
        schedule.schedule_excel_service,
        "get_archive",
        AsyncMock(return_value=archive),
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service, "build_validation_report", building
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service, "get_constraint_setting", get_constraints
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service, "upsert_constraint_setting", upsert
    )
    headers = {"X-Dazah-Page-Key": "production:plan:scheduling"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        validation = await client.get(
            f"/api/v1/production/schedule-excel/{archive.id}/validation",
            headers=headers,
        )
        constraints = await client.get(
            "/api/v1/production/schedule-constraints",
            params={"product": "FA"},
            headers=headers,
        )
        saved_resp = await client.post(
            "/api/v1/production/schedule-constraints",
            params={"product": "FA"},
            json={"standard_cycle_hours": 61, "monthly_dump_target": 26},
            headers=headers,
        )
    assert validation.status_code == 200
    assert validation.json()["data"]["summary"] == {"warn": 0, "info": 0}
    assert constraints.status_code == 200
    assert constraints.json()["data"]["product_code"] == "FA"
    assert saved_resp.status_code == 200
    assert saved_resp.json()["data"]["standard_cycle_hours"] == 61.0
    assert building.await_args.args[1] is archive
    upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_validation_rejects_non_fa_product(monkeypatch):
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        visible_sections=None,
    )
    archive = SimpleNamespace(product_code="MC", rows=[])
    building = AsyncMock()
    monkeypatch.setattr(
        schedule.schedule_excel_service,
        "get_archive",
        AsyncMock(return_value=archive),
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service, "build_validation_report", building
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/production/schedule-excel/{uuid4()}/validation",
            headers={"X-Dazah-Page-Key": "production:plan:scheduling"},
        )
    assert response.status_code == 400
    assert "仅支持 FA" in response.json()["detail"]
    building.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_constraints_maps_value_error_to_400(monkeypatch):
    from app.modules.production import schedule_excel_api as schedule

    app, _ = acceptance_app(
        schedule.router,
        monkeypatch,
        "production:plan:scheduling",
        actions=["sync_config"],
        visible_sections=["FA"],
    )
    monkeypatch.setattr(
        schedule.schedule_validation_service,
        "upsert_constraint_setting",
        AsyncMock(side_effect=ValueError("最大培养周期不能小于标准培养周期")),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/schedule-constraints",
            params={"product": "FA"},
            json={"standard_cycle_hours": 61, "max_cycle_hours": 50},
            headers={"X-Dazah-Page-Key": "production:plan:scheduling"},
        )
    assert response.status_code == 400
    assert "不能小于" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("actions,expected", [(["sensitive_export"], 200), ([], 403)])
async def test_schedule_draft_export_requires_sensitive_export(
    monkeypatch, actions, expected
):
    """草稿导出挂 sensitive_export：未授予该敏感动作时 403 且不触发生成。"""
    from app.modules.production import schedule_draft_api as draft_api

    app, _ = acceptance_app(
        draft_api.router,
        monkeypatch,
        "production:plan:auto-scheduling",
        actions=actions,
    )
    archive = SimpleNamespace(rows=[])
    from io import BytesIO

    composing = Mock(return_value=BytesIO(b"PK-draft"))
    monkeypatch.setattr(
        draft_api.board, "load_latest_archive", AsyncMock(return_value=archive)
    )
    monkeypatch.setattr(
        draft_api.validation, "get_constraint_setting", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        draft_api.board, "list_active_maintenance", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(draft_api.draft, "build_draft_workbook", composing)
    monkeypatch.setattr(
        draft_api.draft,
        "upsert_draft_record",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/schedule-drafts/export",
            json={},
            headers={"X-Dazah-Page-Key": "production:plan:auto-scheduling"},
        )
    assert response.status_code == expected
    if expected == 403:
        composing.assert_not_called()
    else:
        composing.assert_called_once()
        assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_schedule_draft_generate_happy_path(monkeypatch):
    from app.modules.production import schedule_draft_api as draft_api

    app, _ = acceptance_app(
        draft_api.router,
        monkeypatch,
        "production:plan:auto-scheduling",
        actions=["sensitive_export"],
    )
    archive = SimpleNamespace(rows=[])
    monkeypatch.setattr(
        draft_api.board, "load_latest_archive", AsyncMock(return_value=archive)
    )
    monkeypatch.setattr(
        draft_api.validation, "get_constraint_setting", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        draft_api.board, "list_active_maintenance", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        draft_api.draft,
        "upsert_draft_record",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        ok = await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={},
            headers={"X-Dazah-Page-Key": "production:plan:auto-scheduling"},
        )
        await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={},
            headers={"X-Dazah-Page-Key": "production:plan:auto-scheduling"},
        )
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["summary"]["transfer_count"] > 0
    assert isinstance(data["days"], list) and len(data["days"]) >= 28
    assert "validation" in data
    # 无 FA 存档时给出业务 4xx，而不是 500
    monkeypatch.setattr(
        draft_api.board, "load_latest_archive", AsyncMock(return_value=None)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={},
            headers={"X-Dazah-Page-Key": "production:plan:auto-scheduling"},
        )
        bad_period = await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={"period_start": "2026-11-27"},
            headers={"X-Dazah-Page-Key": "production:plan:auto-scheduling"},
        )
    assert missing.status_code == 400
    assert "排产存档" in missing.json()["detail"]
    assert bad_period.status_code == 400
    assert "同时提供" in bad_period.json()["detail"]


@pytest.mark.asyncio
async def test_schedule_draft_period_alignment(monkeypatch):
    """起止日期各自对齐所在扎帐周期；跨月分块、超两月拒绝。"""
    from app.modules.production import schedule_draft_api as draft_api

    app, _ = acceptance_app(
        draft_api.router,
        monkeypatch,
        "production:plan:auto-scheduling",
        actions=["sensitive_export"],
    )
    archive = SimpleNamespace(rows=[])
    monkeypatch.setattr(
        draft_api.board, "load_latest_archive", AsyncMock(return_value=archive)
    )
    monkeypatch.setattr(
        draft_api.validation, "get_constraint_setting", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        draft_api.board, "list_active_maintenance", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        draft_api.draft,
        "upsert_draft_record",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    headers = {"X-Dazah-Page-Key": "production:plan:auto-scheduling"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        aligned = await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={"period_start": "2026-10-20", "period_end": "2026-11-15"},
            headers=headers,
        )
        overlong = await client.post(
            "/api/v1/production/schedule-drafts/generate",
            json={"period_start": "2026-08-20", "period_end": "2026-11-15"},
            headers=headers,
        )
    assert aligned.status_code == 200
    period = aligned.json()["data"]["summary"]["period"]
    assert period == {"start": "2026-09-27", "end": "2026-11-26"}
    assert overlong.status_code == 400
    assert "不能超过两个月" in overlong.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actions,expected",
    [(["sensitive_export", "delete"], 200), ([], 403)],
)
async def test_schedule_draft_records_actions_gate(
    monkeypatch, actions, expected
):
    """草稿历史的下载/删除分别挂 sensitive_export/delete 敏感动作。"""
    from app.modules.production import schedule_draft_api as draft_api

    app, session = acceptance_app(
        draft_api.router,
        monkeypatch,
        "production:plan:auto-scheduling",
        actions=actions,
    )
    record = SimpleNamespace(
        id=uuid4(),
        product_code="FA",
        params={},
        params_hash="hash",
        days=[],
        summary={"period": {"start": "2026-11-27", "end": "2026-12-26"}},
        validation={"summary": {"warn": 0}},
        file_name="草稿.xlsx",
        original_path="schedule_drafts/x.xlsx",
        downloaded_at=datetime(2026, 10, 1, 8, 0, 0),
        created_at=datetime(2026, 10, 1, 7, 0, 0),
        created_by=None,
    )
    getting = AsyncMock(return_value=record)
    listing = AsyncMock(return_value=([], 0))
    deleting = AsyncMock()
    monkeypatch.setattr(draft_api.draft, "get_draft_record", getting)
    monkeypatch.setattr(draft_api.draft, "list_draft_records", listing)
    monkeypatch.setattr(draft_api.draft, "soft_delete_draft_record", deleting)
    monkeypatch.setattr(draft_api, "_record_user_name", AsyncMock(return_value=None))
    headers = {"X-Dazah-Page-Key": "production:plan:auto-scheduling"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_resp = await client.get(
            "/api/v1/production/schedule-drafts/records", headers=headers
        )
        detail = await client.get(
            f"/api/v1/production/schedule-drafts/records/{record.id}",
            headers=headers,
        )
        delete_resp = await client.delete(
            f"/api/v1/production/schedule-drafts/records/{record.id}",
            headers=headers,
        )
    # 列表/详情挂 query：两类授权均可访问
    assert list_resp.status_code == 200
    assert detail.status_code == 200
    # 删除挂 operate+delete
    assert delete_resp.status_code == expected
    if expected == 403:
        deleting.assert_not_awaited()
    else:
        deleting.assert_awaited_once()
