import csv
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import rbac_api
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
async def test_export_uses_business_names_and_neutralizes_spreadsheet_formulas(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), name="=formula", department="采购部")
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [user])
            )
        )
    )
    monkeypatch.setattr(
        rbac_api.PagePermissionRepository,
        "department_labels",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        rbac_api.PagePermissionRepository,
        "list_rollouts",
        AsyncMock(
            return_value=[SimpleNamespace(module_code="procurement", status="draft")]
        ),
    )
    monkeypatch.setattr(
        rbac_api.PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[
                EffectivePageGrantOut(
                    page_key="purchasing:supplier",
                    module_code="procurement",
                    permissions=["access", "query", "operate"],
                    sensitive_actions=["bulk_import"],
                    data_scope=PageDataScopeInput(scope_type="not_applicable"),
                    source="role",
                    source_role_names=["采购经办"],
                ),
            ]
        ),
    )
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
    app.dependency_overrides[rbac_api.require_identity_admin] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/identity/admin/permissions/export")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[1][0] == "'=formula"
    assert rows[1][3] == "采购管理"
    assert rows[1][4:7] == ["是", "是", "是"]
    assert rows[1][8:12] == ["不适用", "角色基线", "采购经办", "草稿（尚未生效）"]
    assert "bulk_import" not in response.text
    assert "purchasing:supplier" not in response.text
    assert "采购" in rows[1][3]
