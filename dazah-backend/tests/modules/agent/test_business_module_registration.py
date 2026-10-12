from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity import deps
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGE_DEFINITIONS
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

OPERATIONS = [
    ("production.list_batches", {}),
    ("production.list_sales_plan_details", {}),
    ("production.list_nonconforming_events", {}),
    ("production.list_shift_logs", {}),
    ("production.list_shift_handovers", {}),
    ("warehouse.list_page_records", {"page_key": "raw-detail"}),
    ("procurement.list_material_catalog", {}),
    ("hr.list_employees", {}),
    ("hr.list_departments", {}),
    ("hr.list_contacts", {}),
    ("hr.list_candidates", {}),
    ("hr.list_onboarding", {}),
    ("hr.list_offboarding", {}),
    ("hr.list_position_transfers", {}),
    ("hr.list_contracts", {}),
    ("hr.list_contract_approval_results", {}),
    ("hr.list_new_employee_training", {}),
    ("hr.list_employee_training_summary", {"department": "生产部"}),
    ("hr.list_trainers", {}),
    ("hr.list_position_training", {}),
    ("hr.list_training_plan_tracking", {}),
    ("registration.list_project_ledger", {"sheet_key": "domestic-associated-review"}),
    ("registration.list_authorization_letters", {}),
    ("registration.list_regulatory_documents", {}),
    ("registration.list_inspection_contacts", {}),
    ("registration.list_knowledge_articles", {}),
    ("registration.read_knowledge_article", {"article_id": str(uuid4())}),
    ("quality.list_lab_instruments", {}),
    ("quality.list_documents", {}),
    ("quality.list_deviation_reports", {}),
    ("quality.list_deviation_investigations", {}),
    ("quality.list_historical_deviations", {}),
    ("quality.list_deviation_workbench_reports", {}),
    ("quality.list_lab_item_inbounds", {}),
    ("quality.list_lab_item_outbounds", {}),
    ("quality.list_oos_oot_reports", {}),
    ("quality.list_oos_oot_investigations", {}),
    ("quality.list_oot_ledger", {}),
    ("quality.list_oot_limit_products", {}),
    ("quality.list_product_departments", {}),
    ("quality.list_finished_product_anomalies", {}),
    ("quality.list_qc_validations", {}),
    ("quality.list_validation_reviews", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "params"), OPERATIONS)
async def test_registered_module_queries_require_their_own_page_grant(
    monkeypatch, operation, params
):
    ensure_agent_tools_registered()
    spec = tool_registry.require(operation)
    assert not spec.write
    assert spec.permission_key == "module.agent.read"
    page_key = spec.page_keys[0]
    grant = EffectivePageGrantOut(
        page_key=page_key,
        module_code=spec.module,
        permissions=["access", "query"],
        sensitive_actions=[],
        data_scope=PageDataScopeInput(scope_type="department_tree"),
        source="user",
    )
    grants = AsyncMock(return_value=[grant])
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    request = AgentToolExecuteRequest.model_validate(
        {
            "operation": operation,
            "params": params,
            "subject": {"tenant_id": "local", "user_id": uuid4(), "source": "internal"},
            "execution_context": {"page_key": page_key},
        }
    )
    validated = spec.input_model.model_validate(params)
    actor = SimpleNamespace(id=uuid4(), role="user")
    result = await ToolExecutor._resolve_tool_page_grant(
        None,
        spec=spec,
        request=request,
        validated=validated,
        user=actor,
    )
    assert result == grant
    grants.return_value = []
    with pytest.raises(HTTPException) as error:
        await ToolExecutor._resolve_tool_page_grant(
            None,
            spec=spec,
            request=request,
            validated=validated,
            user=actor,
        )
    assert error.value.status_code == 403
    with pytest.raises(ValidationError):
        spec.input_model.model_validate({**params, "page_size": 101})


@pytest.mark.asyncio
async def test_module_coverage_http_projects_new_providers_and_rejects_non_admin(
    monkeypatch,
):
    ensure_agent_tools_registered()
    specs = tool_registry.list()
    rows = [
        SimpleNamespace(
            operation=spec.name,
            status="active",
            admin_enabled=True,
            is_deleted=False,
        )
        for spec in specs
    ]
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: rows),
            )
        )
    )
    actor = SimpleNamespace(role="admin", status="active", is_deleted=False)
    monkeypatch.setattr(ToolCatalogService, "synchronize", AsyncMock())
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[
                SimpleNamespace(page_key=p.page_key) for p in PAGE_DEFINITIONS
            ],
        ),
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/agent")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/agent/control/module-coverage")
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["registered_count"] == len(specs)
        modules = {m["module_code"]: m for m in payload["modules"]}
        for code in (
            "production",
            "warehouse",
            "procurement",
            "hr",
            "registration",
            "quality",
        ):
            assert modules[code]["state"] in {"partial", "integrated"}
            assert modules[code]["registered_count"] > 0
        assert (
            modules["procurement"]["covered_pages"]
            == modules["procurement"]["total_pages"]
        )
        assert modules["production"]["state"] == "integrated"
        assert modules["production"]["covered_pages"] == 21
        assert modules["production"]["total_pages"] == 21
        assert modules["production"]["coverage_percent"] == 100.0
        assert modules["production"]["registered_count"] == 10
        assert all(page["enabled_count"] > 0 for page in modules["production"]["pages"])
        assert modules["warehouse"]["state"] == "integrated"
        assert modules["warehouse"]["covered_pages"] == 47
        assert modules["warehouse"]["total_pages"] == 47
        assert modules["warehouse"]["coverage_percent"] == 100.0
        assert modules["warehouse"]["registered_count"] == 7
        assert all(page["enabled_count"] > 0 for page in modules["warehouse"]["pages"])
        assert modules["registration"]["state"] == "integrated"
        assert modules["registration"]["covered_pages"] == 20
        assert modules["registration"]["total_pages"] == 20
        assert modules["registration"]["coverage_percent"] == 100.0
        assert modules["registration"]["registered_count"] == 9
        assert all(
            page["enabled_count"] > 0 for page in modules["registration"]["pages"]
        )
        assert modules["quality"]["state"] == "integrated"
        assert modules["quality"]["covered_pages"] == 59
        assert modules["quality"]["total_pages"] == 59
        assert modules["quality"]["coverage_percent"] == 100.0
        assert modules["quality"]["registered_count"] == 89
        assert all(page["enabled_count"] > 0 for page in modules["quality"]["pages"])
        assert modules["hr"]["state"] == "integrated"
        assert modules["hr"]["covered_pages"] == 17
        assert modules["hr"]["total_pages"] == 17
        assert modules["hr"]["coverage_percent"] == 100.0
        assert modules["hr"]["registered_count"] == 16
        assert all(page["enabled_count"] > 0 for page in modules["hr"]["pages"])
        assert payload["covered_pages"] == 228
        actor.role = "user"
        denied = await client.get("/api/v1/agent/control/module-coverage")
        assert denied.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("sections", [None, [], ["MC"], ["sales_plan"]])
async def test_overview_executor_preserves_card_grants_and_resets_context(
    monkeypatch, sections
):
    from app.modules.production.repository import ProductionRepository
    from app.platform.identity.data_scope import (
        current_page_key,
        current_page_visible_sections,
    )

    ensure_agent_tools_registered()
    spec = tool_registry.require("production.list_sales_plan_details")
    query = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(ProductionRepository, "get_sales_plan_details", query)
    grant = EffectivePageGrantOut(
        page_key="production:overview",
        module_code="production",
        permissions=["access", "query"],
        sensitive_actions=[],
        visible_sections=sections,
        data_scope=PageDataScopeInput(scope_type="all"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    user = SimpleNamespace(id=uuid4(), role="user")
    request = AgentToolExecuteRequest.model_validate(
        {
            "operation": spec.name,
            "subject": {"tenant_id": "local", "user_id": user.id, "source": "internal"},
            "execution_context": {"page_key": "production:overview"},
        }
    )
    page = current_page_key.set("outer-page")
    previous = current_page_visible_sections.set(["outer-section"])
    try:
        invoke = ToolExecutor()._invoke_tool(
            object(),
            spec=spec,
            request=request,
            validated=spec.input_model(),
            session_id=None,
            user_id=user.id,
            user=user,
            agent_service=None,
        )
        if sections is not None and "sales_plan" not in sections:
            with pytest.raises(HTTPException) as error:
                await invoke
            assert error.value.status_code == 403
            query.assert_not_awaited()
        else:
            result = await invoke
            assert result.ok and result.data["meta"]["total"] == 0
            query.assert_awaited_once()
        assert current_page_key.get() == "outer-page"
        assert current_page_visible_sections.get() == ["outer-section"]
    finally:
        current_page_key.reset(page)
        current_page_visible_sections.reset(previous)
