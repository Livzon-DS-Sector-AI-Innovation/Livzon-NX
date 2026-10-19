"""Certificate deletion is a separate action, including after revocation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.registration.api import certificates
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
async def test_certificate_delete_requires_separate_action(monkeypatch):
    app = FastAPI()
    app.include_router(
        certificates.router,
        prefix="/api/v1/registration/certificate-management",
        dependencies=[Depends(deps.require_module_view("registration"))],
    )
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
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
    page = "registration:certificate-management:international-registration"
    grant = EffectivePageGrantOut(
        page_key=page,
        module_code="registration",
        permissions=["access", "query", "operate"],
        data_scope=PageDataScopeInput(scope_type="all"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    delete = AsyncMock()
    monkeypatch.setattr(certificates.CertificateWorkbookService, "delete_entry", delete)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def request():
            return await client.delete(
                f"/api/v1/registration/certificate-management/entries/{uuid4()}",
                headers={"X-Dazah-Page-Key": page},
            )

        assert (await request()).status_code == 403
        delete.assert_not_awaited()
        grant.sensitive_actions = ["delete"]
        response = await request()
        assert response.status_code == 200, response.text
        delete.assert_awaited_once()
        grant.sensitive_actions = []
        assert (await request()).status_code == 403
        delete.assert_awaited_once()
