from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.automation_schema import compile_automation_definition
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.schemas import AgentToolExecuteRequest, AgentTrustedSubject
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import (
    AgentToolSpec,
    EmptyToolInput,
    ToolExecutor,
    ToolRegistry,
    tool_registry,
)


@pytest.mark.parametrize(
    ("path", "pages"),
    [
        ("/identity/personnel", ()),
        ("/api/v1/identity/personnel", ()),
        ("/system/users", ()),
        ("/settings/roles", ("system:roles",)),
        ("/energy/feishu-config", ()),
        ("/energy/feishu/roots/{root_id}", ()),
        ("/agent/operations/report", ()),
        ("/warehouse/feishu/ws/restart", ("warehouse:warehouse-settings",)),
        (
            "/quality/feishu-sync/pull",
            ("quality:quality-settings", "quality:deviations:deviation-ledger"),
        ),
    ],
)
def test_settings_aliases_cannot_register(path, pages):
    registry = ToolRegistry()
    spec = AgentToolSpec(
        name="alias.harmless_name",
        summary="别名",
        input_model=EmptyToolInput,
        handler=AsyncMock(),
        path=path,
        page_keys=pages,
    )
    registry.register(spec)
    assert registry.get(spec.name) is None
    assert registry.list() == []
    assert registry.excluded()[0][0] is spec
    with pytest.raises(HTTPException) as rejected:
        registry.require(spec.name)
    assert rejected.value.status_code == 400
    registry.clear()
    assert registry.excluded() == []


def test_registered_inventory_keeps_business_and_personal_tools():
    ensure_agent_tools_registered()
    assert tool_registry.get("identity.get_department_tree") is None
    assert tool_registry.get("identity.search_personnel") is None
    assert tool_registry.get("identity.check_feishu_permissions") is None
    assert tool_registry.get("warehouse.get_feishu_ws_status") is None
    assert tool_registry.get("agent.get_operations_report") is None
    for operation in (
        "analytics.aggregate",
        "quality.list_deviations",
        "warehouse.list_products",
        "agent.create_automation",
        "agent.list_attachments",
        "identity.deliver_feishu_message",
    ):
        assert tool_registry.get(operation) is not None
    assert all(spec.module is None or spec.page_keys for spec in tool_registry.list())
    assert tool_registry.get("energy.get_overview") is None


@pytest.mark.asyncio
async def test_retired_catalog_record_is_disabled_and_cannot_be_reenabled():
    ensure_agent_tools_registered()
    row = SimpleNamespace(
        operation="identity.check_feishu_permissions",
        status="active",
        admin_enabled=True,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [row])
            )
        ),
        scalar=AsyncMock(return_value=row),
        add=lambda value: None,
        flush=AsyncMock(),
    )
    service = ToolCatalogService()
    await service.synchronize(db)
    assert row.status == "disabled"
    assert row.admin_enabled is False
    with pytest.raises(HTTPException) as rejected:
        await service.set_enabled(db, operation=row.operation, enabled=True)
    assert rejected.value.status_code == 409
    assert row.status == "disabled"
    assert row.admin_enabled is False


@pytest.mark.asyncio
async def test_catalog_confirmation_metadata_matches_draft_and_business_tools():
    ensure_agent_tools_registered()
    projected = {}
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=list))
        ),
        add=lambda row: projected.update({row.operation: row}),
        flush=AsyncMock(),
    )
    await ToolCatalogService().synchronize(db)
    for operation in (
        "agent.create_automation",
        "agent.create_automation_draft",
        "agent.create_scheduled_task",
    ):
        assert projected[operation].write is True
        assert projected[operation].confirmation_required is False
    assert (
        projected["procurement.create_purchase_request"].confirmation_required is True
    )
    assert projected["quality.list_deviations"].confirmation_required is False


@pytest.mark.asyncio
async def test_settings_execution_http_rejects_even_administrator(monkeypatch):
    ensure_agent_tools_registered()
    from app.modules.agent.service import AgentService

    service = AgentService(get_settings())
    db = SimpleNamespace(get=AsyncMock(), execute=AsyncMock())
    monkeypatch.setattr(api, "AgentService", lambda settings: service)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/agent")
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        AGENT_TOOL_TOKEN="exclusion-test-token"
    )
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/agent/tools/execute",
            headers={"Authorization": "Bearer exclusion-test-token"},
            json={
                "operation": "identity.check_feishu_permissions",
                "params": {},
                "subject": {
                    "user_id": "00000000-0000-0000-0000-000000000001",
                    "tenant_id": "local",
                    "source": "web",
                },
            },
        )
    assert response.status_code == 400
    assert "registry" in response.json()["detail"]
    db.get.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_confirmation_cannot_execute_removed_configuration():
    ensure_agent_tools_registered()
    request = AgentToolExecuteRequest(
        operation="warehouse.restart_feishu_ws",
        subject=AgentTrustedSubject(
            user_id="00000000-0000-0000-0000-000000000001",
            tenant_id="local",
            source="web",
        ),
    )
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as rejected:
        await ToolExecutor().execute_confirmed(
            db,
            request=request,
            current_user=SimpleNamespace(role="admin"),
            confirmation=SimpleNamespace(id="old-confirmation"),
        )
    assert rejected.value.status_code == 400
    db.execute.assert_not_awaited()


def test_old_automation_cannot_compile_removed_configuration():
    ensure_agent_tools_registered()
    report = compile_automation_definition(
        {
            "name": "旧配置任务",
            "steps": [
                {
                    "key": "config",
                    "type": "tool",
                    "operation": "warehouse.restart_feishu_ws",
                    "input": {},
                },
                {"key": "end", "type": "end", "status": "succeeded"},
            ],
        },
        capabilities={spec.name: spec.public_dict() for spec in tool_registry.list()},
    )
    assert any(issue.code == "automation.unknown_operation" for issue in report.issues)
