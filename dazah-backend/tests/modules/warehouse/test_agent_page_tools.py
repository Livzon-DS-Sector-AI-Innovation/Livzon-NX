from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.modules.warehouse import agent_tools as tools
from app.modules.warehouse.page_access import assert_material_page
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGES_BY_MODULE
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

SUMMARY_OPERATIONS = [
    ("get_inventory_summary", "get_inventory_summary", {"raw_materials": {"total": 3}}),
    ("get_trend_summary", "get_trend_anomaly_summary", {"total": 2, "high_risk": 1}),
    (
        "get_hardware_cost_summary",
        "get_hardware_cost_summary",
        {"anomaly_workshops": 1},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "method", "expected"), SUMMARY_OPERATIONS)
async def test_summary_executor_requires_ai_page_and_calls_matching_service(
    monkeypatch, operation, method, expected
):
    ensure_agent_tools_registered()
    query = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        tools, "WarehouseAIService", lambda db: SimpleNamespace(**{method: query})
    )
    spec = tool_registry.require(f"warehouse.{operation}")
    assert spec.page_keys == ("warehouse:ai-analysis",)
    assert not spec.write and spec.risk_level == "low"
    grant = EffectivePageGrantOut(
        page_key="warehouse:ai-analysis",
        module_code="warehouse",
        permissions=["access", "query"],
        sensitive_actions=[],
        data_scope=PageDataScopeInput(scope_type="all"),
        source="user",
    )
    grants = AsyncMock(return_value=[grant])
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    actor = SimpleNamespace(id=uuid4(), role="user")
    request = AgentToolExecuteRequest.model_validate(
        {
            "operation": spec.name,
            "params": {},
            "subject": {
                "tenant_id": "local",
                "user_id": actor.id,
                "source": "internal",
            },
            "execution_context": {"page_key": "warehouse:ai-analysis"},
        }
    )
    kwargs = dict(
        spec=spec,
        request=request,
        validated=spec.input_model(),
        session_id=None,
        user_id=actor.id,
        user=actor,
        agent_service=None,
    )
    result = await ToolExecutor()._invoke_tool(object(), **kwargs)
    assert result.ok and result.data == expected
    query.assert_awaited_once_with()
    query.reset_mock()
    for permissions in (["access"], []):
        grants.return_value = [grant.model_copy(update={"permissions": permissions})]
        with pytest.raises(HTTPException) as error:
            await ToolExecutor()._invoke_tool(object(), **kwargs)
        assert error.value.status_code == 403
        query.assert_not_awaited()
    grants.return_value = [
        grant.model_copy(update={"page_key": "warehouse:materials:raw-summary"})
    ]
    with pytest.raises(HTTPException) as error:
        await ToolExecutor()._invoke_tool(object(), **kwargs)
    assert error.value.status_code == 403
    query.assert_not_awaited()


def test_summary_input_rejects_scope_or_force_overrides():
    for params in (
        {"force": True},
        {"page_key": "raw-detail"},
        {"user_id": str(uuid4())},
    ):
        with pytest.raises(ValidationError):
            tools.WarehouseSummaryInput.model_validate(params)


def test_warehouse_bindings_cover_all_business_pages_and_exclude_settings():
    ensure_agent_tools_registered()
    specs = [spec for spec in tool_registry.list() if spec.module == "warehouse"]
    covered = {key for spec in specs for key in spec.page_keys}
    expected = {
        page.page_key
        for page in PAGES_BY_MODULE["warehouse"]
        if page.page_key != "warehouse:warehouse-settings"
    }
    assert len(specs) == 7
    assert len(expected) == 47 and covered == expected
    assert all(not spec.write for spec in specs)


class Page(BaseModel):
    rows: list[dict[str, str]]


@pytest.mark.asyncio
async def test_page_query_reads_only_local_bounded_snapshot(monkeypatch):
    query = AsyncMock(return_value=Page(rows=[{"物料名称": "葡萄糖"}]))
    monkeypatch.setattr(
        tools,
        "_warehouse_service",
        lambda context: SimpleNamespace(get_feishu_material_page=query),
    )
    result = await tools.list_page_records(
        SimpleNamespace(db=object()),
        tools.WarehousePageRecordsInput(
            page_key="raw-detail", keyword="葡萄糖", page=2, page_size=10
        ),
    )
    assert result == {"rows": [{"物料名称": "葡萄糖"}]}
    query.assert_awaited_once_with(
        "raw-detail", keyword="葡萄糖", page=2, page_size=10, source="local"
    )


def test_page_alias_cannot_target_another_menu():
    token = current_page_key.set("warehouse:materials:raw-detail")
    try:
        assert_material_page("raw-detail")
        with pytest.raises(HTTPException) as error:
            assert_material_page("packaging-detail")
        assert error.value.status_code == 403
    finally:
        current_page_key.reset(token)


def test_unknown_page_alias_is_rejected_before_service_call():
    with pytest.raises(ValidationError):
        tools.WarehousePageRecordsInput(page_key="unknown")
    schema = tools.WarehousePageRecordsInput.model_json_schema()
    assert "raw-detail" in schema["properties"]["page_key"]["enum"]
