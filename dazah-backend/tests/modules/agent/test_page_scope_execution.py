from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity.models import User
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_scope_sync_generator_initializes_and_tracks_outbox(monkeypatch, failed):
    from app.modules.agent.scheduled import AgentAccessScopeSyncGenerator

    generator = AgentAccessScopeSyncGenerator(batch_size=20)
    assert generator.batch_size == 20
    assert isinstance(generator.scope_service, AgentAccessScopeService)
    synchronize = AsyncMock(
        side_effect=RuntimeError("scope sync failed") if failed else None
    )
    processed = AsyncMock()
    mark_failed = AsyncMock()
    monkeypatch.setattr(generator.scope_service, "synchronize", synchronize)
    monkeypatch.setattr(generator.permission_repo, "mark_outbox_processed", processed)
    monkeypatch.setattr(generator.permission_repo, "mark_outbox_failed", mark_failed)
    actor_id = uuid4()
    item = SimpleNamespace(user_id=uuid4(), updated_by=actor_id, created_by=uuid4())
    session = object()

    await generator.execute_one(session, item)

    synchronize.assert_awaited_once_with(
        session, user_id=item.user_id, actor_id=actor_id
    )
    if failed:
        processed.assert_not_awaited()
        mark_failed.assert_awaited_once_with(
            session, item, error="scope sync failed", actor_id=actor_id
        )
    else:
        processed.assert_awaited_once_with(session, item, actor_id=actor_id)
        mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_scope_follows_pages_without_legacy_module_grants(monkeypatch):
    from app.modules.agent.tool_registration import ensure_agent_tools_registered
    from app.platform.identity.page_permissions import PagePermissionService

    ensure_agent_tools_registered()
    service = AgentAccessScopeService()
    user = SimpleNamespace(id=uuid4(), role="user", grant_version=1, is_deleted=False)
    grants = [
        EffectivePageGrantOut(
            page_key="quality:deviations:deviation-ledger",
            module_code="quality",
            permissions=["access", "query"],
            sensitive_actions=[],
            data_scope=PageDataScopeInput(scope_type="department_tree"),
            source="role",
        )
    ]
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(side_effect=lambda *a, **kw: grants),
    )
    monkeypatch.setattr(service, "get_snapshot", AsyncMock(return_value=None))
    db = SimpleNamespace(
        get=AsyncMock(return_value=user), add=Mock(), flush=AsyncMock()
    )
    snapshot = await service.synchronize(db, user_id=user.id)
    assert [module["module_code"] for module in snapshot.modules] == ["quality"]
    assert "quality.list_deviations" in snapshot.tool_names
    assert "quality.list_deviations" in snapshot.workflow_tool_names
    assert "procurement.list_purchase_requests" not in snapshot.tool_names
    assert all(
        not tool_registry.require(name).write
        for name in snapshot.tool_names
        if tool_registry.require(name).module == "quality"
    )
    grants.clear()
    user.grant_version += 1
    revoked = await service.synchronize(db, user_id=user.id)
    assert revoked.modules == []
    assert "quality.list_deviations" not in revoked.tool_names
    assert "quality.list_deviations" not in revoked.workflow_tool_names


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
async def test_saved_page_grant_authorizes_tool_without_publication(monkeypatch):
    spec = tool_registry.require("procurement.list_purchase_requests")
    monkeypatch.setattr(
        "app.modules.agent.tools.PagePermissionService.effective_grants",
        AsyncMock(
            return_value=[
                EffectivePageGrantOut(
                    page_key=spec.page_keys[0],
                    module_code="procurement",
                    permissions=["access", "query"],
                    sensitive_actions=[],
                    data_scope=PageDataScopeInput(scope_type="department_tree"),
                    source="user",
                )
            ]
        ),
    )
    grant = await ToolExecutor._resolve_tool_page_grant(
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
    assert grant.page_key == spec.page_keys[0]


@pytest.mark.asyncio
async def test_legacy_page_context_resolves_to_current_tool_grant(monkeypatch):
    spec = tool_registry.require("warehouse.list_products")
    current_page_key = spec.page_keys[0]
    legacy_page_key = current_page_key.replace(
        "warehouse:product-inventory:", "warehouse:product:", 1
    )
    monkeypatch.setattr(
        "app.modules.agent.tools.PagePermissionService.effective_grants",
        AsyncMock(
            return_value=[
                EffectivePageGrantOut(
                    page_key=current_page_key,
                    module_code="warehouse",
                    permissions=["access", "query"],
                    sensitive_actions=[],
                    data_scope=PageDataScopeInput(scope_type="department_tree"),
                    source="user",
                )
            ]
        ),
    )
    grant = await ToolExecutor._resolve_tool_page_grant(
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
                "execution_context": {"page_key": legacy_page_key},
            }
        ),
        validated=spec.input_model.model_validate({}),
        user=SimpleNamespace(id=uuid4(), role="user"),
    )
    assert grant.page_key == current_page_key


@pytest.mark.asyncio
async def test_admin_tool_permission_does_not_query_page_grants(monkeypatch):
    spec = tool_registry.require("procurement.list_purchase_requests")
    page_grants = AsyncMock(
        side_effect=AssertionError("administrator does not use page grants")
    )
    monkeypatch.setattr(
        "app.modules.agent.tools.PagePermissionService.effective_grants", page_grants
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
    page_grants.assert_not_awaited()


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
