from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.core.database import get_db
from app.modules.hr import api
from app.modules.hr.service import PositionTransferRecordService
from app.platform.identity import data_scope, deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
async def test_pending_approvals_apply_department_scope_and_current_signer() -> None:
    records = [
        SimpleNamespace(
            approval_flow={
                "current_step": 0,
                "steps": [{"signer_open_id": "test-actor"}],
            }
        ),
        SimpleNamespace(
            approval_flow={"current_step": 0, "steps": [{"signer": "其他审批人"}]}
        ),
    ]
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: records)
    )
    service = PositionTransferRecordService(session)
    rows, total = await service.list_approvals(
        current_user=SimpleNamespace(name="本人", feishu_open_id="test-actor"),
        tab="pending_approval",
        dept_alias_set={"测试车间"},
        page=1,
        page_size=5,
    )
    assert rows == [records[0]]
    assert total == 1
    sql = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "department_before IN ('测试车间')" in sql
    assert "apply_department IN ('测试车间')" in sql
    assert "待审批" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [True, False])
async def test_transfer_todo_route_uses_page_authorization_and_department_scope(
    monkeypatch: pytest.MonkeyPatch, authorized: bool
) -> None:
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(deps.require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id="test-user", role="user", name="测试审批人"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    listing = AsyncMock(return_value=([], 0))
    app.dependency_overrides[api.get_position_transfer_service] = lambda: (
        SimpleNamespace(list_approvals=listing)
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key="hr:position-transfer",
        module_code="hr",
        permissions=["access", "query"] if authorized else [],
        source="user",
        data_scope=PageDataScopeInput(
            scope_type="departments",
            department_ids=["00000000-0000-0000-0000-000000000001"],
        ),
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    monkeypatch.setattr(
        data_scope,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=data_scope.DepartmentScope(department_names={"授权车间"})
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.get(
            "/api/v1/hr/position-transfers/approvals?tab=pending_approval",
            headers={"X-Dazah-Page-Key": "hr:position-transfer"},
        )
    assert result.status_code == (200 if authorized else 403)
    if authorized:
        assert result.json()["data"] == []
        assert listing.call_args.kwargs["dept_alias_set"] == {"授权车间"}
        assert listing.call_args.kwargs["tab"] == "pending_approval"
    else:
        listing.assert_not_awaited()
