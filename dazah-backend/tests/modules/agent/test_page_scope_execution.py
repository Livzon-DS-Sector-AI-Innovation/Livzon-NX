from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity.models import User


@pytest.mark.asyncio
async def test_lifecycle_retirement_expires_existing_tool_snapshot(monkeypatch):
    from copy import deepcopy

    from app.platform.identity import page_lifecycle

    service = AgentAccessScopeService()
    user = SimpleNamespace(
        id=uuid4(), status="active", is_deleted=False, grant_version=2
    )
    before = service.current_registry_version()
    snapshot = SimpleNamespace(
        sync_status="synced",
        source_grant_version=2,
        registry_version=before,
        tool_names=["procurement.list_purchase_requests"],
        workflow_tool_names=[],
    )
    monkeypatch.setattr(service, "get_snapshot", AsyncMock(return_value=snapshot))
    ledger = deepcopy(page_lifecycle.load_ledger())
    ledger["pages"]["quality:deviations:deviation-ledger"]["status"] = "retired"
    monkeypatch.setattr(page_lifecycle, "load_ledger", lambda: ledger)
    assert service.current_registry_version() != before
    with pytest.raises(HTTPException) as error:
        await service.require_tool_access(
            None,
            user=user,
            tool_name="procurement.list_purchase_requests",
            module="procurement",
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stale_field", ["registry_version", "source_grant_version", "sync_status"]
)
async def test_execution_rejects_stale_scope_without_rebuilding(
    monkeypatch, stale_field
):
    service = AgentAccessScopeService()
    user = SimpleNamespace(
        id=uuid4(), status="active", is_deleted=False, grant_version=2
    )
    snapshot = SimpleNamespace(
        sync_status="synced",
        source_grant_version=2,
        registry_version="current",
        tool_names=["procurement.list_purchase_requests"],
        workflow_tool_names=[],
    )
    setattr(
        snapshot, stale_field, 1 if stale_field == "source_grant_version" else "stale"
    )
    monkeypatch.setattr(service, "get_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(service, "current_registry_version", lambda: "current")
    rebuild = AsyncMock()
    monkeypatch.setattr(service, "synchronize", rebuild)
    with pytest.raises(HTTPException) as error:
        await service.require_tool_access(
            None,
            user=user,
            tool_name="procurement.list_purchase_requests",
            module="procurement",
        )
    assert error.value.status_code == 403
    rebuild.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_snapshot_still_requires_workflow_permission(monkeypatch):
    service = AgentAccessScopeService()
    user = SimpleNamespace(
        id=uuid4(), status="active", is_deleted=False, grant_version=2
    )
    snapshot = SimpleNamespace(
        sync_status="synced",
        source_grant_version=2,
        registry_version="current",
        tool_names=["procurement.approve_purchase_request"],
        workflow_tool_names=[],
    )
    monkeypatch.setattr(service, "get_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(service, "current_registry_version", lambda: "current")
    assert (
        await service.require_tool_access(
            None,
            user=user,
            tool_name="procurement.approve_purchase_request",
            module="procurement",
        )
        is snapshot
    )
    with pytest.raises(HTTPException) as error:
        await service.require_tool_access(
            None,
            user=user,
            tool_name="procurement.approve_purchase_request",
            module="procurement",
            for_workflow=True,
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_unpublished_business_tool_cannot_fall_back_to_legacy_grant(monkeypatch):
    spec = tool_registry.require("procurement.list_purchase_requests")
    monkeypatch.setattr(
        "app.modules.agent.tools.PagePermissionRepository.get_rollout",
        AsyncMock(return_value=SimpleNamespace(status="draft")),
    )
    with pytest.raises(HTTPException) as error:
        await ToolExecutor._resolve_tool_page_grant(
            None,
            spec=spec,
            request=AgentToolExecuteRequest.model_validate(
                {
                    "operation": spec.name,
                    "subject": {
                        "tenant_id": "local",
                        "user_id": uuid4(),
                        "source": "internal",
                    },
                }
            ),
            validated=spec.input_model.model_validate({}),
            user=SimpleNamespace(id=uuid4(), role="user"),
        )
    assert error.value.status_code == 403
    assert "尚未发布" in error.value.detail


@pytest.mark.asyncio
async def test_admin_tool_permission_does_not_require_page_publication(monkeypatch):
    spec = tool_registry.require("procurement.list_purchase_requests")
    rollout = AsyncMock(
        side_effect=AssertionError("administrator does not use page grants")
    )
    monkeypatch.setattr(
        "app.modules.agent.tools.PagePermissionRepository.get_rollout", rollout
    )
    user = SimpleNamespace(id=uuid4(), role="admin")
    grant = await ToolExecutor._resolve_tool_page_grant(
        None,
        spec=spec,
        request=AgentToolExecuteRequest.model_validate(
            {
                "operation": spec.name,
                "subject": {
                    "tenant_id": "local",
                    "user_id": user.id,
                    "source": "internal",
                },
            }
        ),
        validated=spec.input_model.model_validate({}),
        user=user,
    )
    assert grant is None
    rollout.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_snapshot_has_all_registered_tools_but_keeps_workflow_limits(
    db_session,
):
    admin = User(name="系统管理员工具测试", role="admin")
    db_session.add(admin)
    await db_session.flush()
    service = AgentAccessScopeService()
    snapshot = await service.synchronize(db_session, user_id=admin.id)
    specs = tool_registry.list()
    assert set(snapshot.tool_names) == {spec.name for spec in specs}
    assert set(snapshot.workflow_tool_names) == {
        spec.name
        for spec in specs
        if spec.workflow_allowed and not spec.human_decision_required
    }
    admin.role = "user"
    admin.grant_version += 1
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await service.require_tool_access(
            db_session,
            user=admin,
            tool_name="procurement.list_purchase_requests",
            module="procurement",
        )
    assert error.value.status_code == 403
    updated = await service.synchronize(db_session, user_id=admin.id)
    assert "procurement.list_purchase_requests" not in updated.tool_names
