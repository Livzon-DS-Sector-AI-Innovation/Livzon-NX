from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.hr import contract_api
from app.modules.hr.contract_repository import ContractRepository
from app.platform.identity import data_scope, deps, page_policy, rbac
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize("department,expected", [("范围外", 403), ("范围内", 200)])
async def test_contract_page_scope_cannot_be_expanded_by_legacy_write(
    monkeypatch, department, expected
):
    key = "hr:contracts:contracts-ledger"
    app = FastAPI()
    app.include_router(
        contract_api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(deps.require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
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
        page_key=key,
        module_code="hr",
        permissions=["access", "query"],
        sensitive_actions=[],
        data_scope=PageDataScopeInput(
            scope_type="departments", department_ids=[str(uuid4())]
        ),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        rbac, "resolve_user_permissions", AsyncMock(return_value=["hr:write"])
    )
    monkeypatch.setattr(
        data_scope,
        "resolve_user_department_scope",
        AsyncMock(return_value=data_scope.DepartmentScope(department_names={"范围内"})),
    )
    listing = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(ContractRepository, "list", listing)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/hr/contracts",
            params={"department": department},
            headers={"X-Dazah-Page-Key": key},
        )
    assert response.status_code == expected
    if expected == 403:
        listing.assert_not_awaited()
    else:
        assert listing.call_args.kwargs["dept_alias_set"] == {"范围内"}


@pytest.mark.asyncio
async def test_contract_detail_and_update_keep_department_scope(
    monkeypatch, db_session
):
    from app.core.exceptions import ForbiddenException
    from app.modules.hr import contract_repository, contract_service
    from app.modules.hr.contract_schemas import ContractManagementUpdate
    from app.modules.hr.models import ContractManagement

    resolve = AsyncMock(
        return_value=data_scope.DepartmentScope(department_names={"范围内"})
    )
    monkeypatch.setattr(contract_repository, "resolve_user_department_scope", resolve)
    monkeypatch.setattr(contract_service, "resolve_user_department_scope", resolve)
    own = ContractManagement(
        employee_number="ACCEPTANCE-OWN", name="验收员工", dept_level1="范围内"
    )
    foreign = ContractManagement(
        employee_number="ACCEPTANCE-OTHER", name="验收员工", dept_level1="范围外"
    )
    db_session.add_all([own, foreign])
    await db_session.flush()
    actor = data_scope.current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    page = data_scope.current_page_key.set("hr:contracts:contracts-ledger")
    try:
        service = contract_service.ContractService(db_session)
        push = AsyncMock()
        monkeypatch.setattr(service, "_sync_push_update", push)
        assert await service.repo.get_by_id(foreign.id) is None
        rows, _ = await service.repo.list()
        assert own in rows and foreign not in rows
        with pytest.raises(ValueError):
            await service.update(
                foreign.id, ContractManagementUpdate(position="changed")
            )
        with pytest.raises(ForbiddenException):
            await service.update(own.id, ContractManagementUpdate(dept_level1="范围外"))
        push.assert_not_awaited()
        assert own.dept_level1 == "范围内"
        result = await service.update(
            own.id, ContractManagementUpdate(position="已授权修改")
        )
        assert result.position == "已授权修改"
        push.assert_awaited_once()
    finally:
        data_scope.current_page_key.reset(page)
        data_scope.current_page_actor.reset(actor)


@pytest.mark.asyncio
async def test_legacy_hr_write_guard_uses_the_current_page_grant(monkeypatch):
    from app.core.exceptions import AppException
    from app.modules.hr.api import _assert_hr_write

    key = "hr:contracts:contracts-ledger"
    token = data_scope.current_page_key.set(key)
    grants = AsyncMock(
        return_value=[SimpleNamespace(page_key=key, permissions=["operate"])]
    )
    legacy = AsyncMock(return_value=["hr:write"])
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    monkeypatch.setattr(rbac, "resolve_user_permissions", legacy)
    try:
        user = SimpleNamespace(id=uuid4(), role="user")
        await _assert_hr_write(AsyncMock(), user)
        grants.return_value = []
        with pytest.raises(AppException) as error:
            await _assert_hr_write(AsyncMock(), user)
        assert error.value.status_code == 403
        legacy.assert_not_awaited()
    finally:
        data_scope.current_page_key.reset(token)
