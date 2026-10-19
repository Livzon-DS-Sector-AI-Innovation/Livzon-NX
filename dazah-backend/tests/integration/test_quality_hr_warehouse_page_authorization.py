"""Real HTTP routes honor page grants on grant, save and subsequent revocation.

All business services and sessions are mocks; no database or Feishu is accessed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.hr import api as hr
from app.modules.quality.api import validation_review as quality
from app.modules.warehouse import api as warehouse
from app.platform.identity import deps, page_policy, rbac
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["quality", "hr", "warehouse"])
async def test_page_grant_lifecycle_without_legacy_write(monkeypatch, module):
    configurations = {
        "quality": (
            quality.router,
            "quality:validation:validation-ai-review",
            "POST",
            "/validation-reviews",
            {"title": "权限验证"},
            [],
        ),
        "hr": (
            hr.router,
            "hr:hr-settings:hr-settings-dept-mapping",
            "PUT",
            f"/training/dept-mappings/{uuid4()}",
            {},
            ["sync_config"],
        ),
        "warehouse": (
            warehouse.router,
            "warehouse:warehouse-settings",
            "POST",
            "/feishu-config/test",
            None,
            ["sync_config"],
        ),
    }
    router, page, method, path, payload, actions = configurations[module]
    app = FastAPI()
    app.include_router(
        router,
        prefix=f"/api/v1/{module}",
        dependencies=[
            Depends(deps.require_module_view(module)),
        ],
    )
    session = SimpleNamespace(commit=AsyncMock())
    actor = SimpleNamespace(id=uuid4(), role="user", name="测试用户")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[deps.get_current_user] = lambda: actor
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all",
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=page,
        module_code=module,
        permissions=["access", "query"],
        data_scope=PageDataScopeInput(scope_type="all"),
        source="user",
    )
    effective = AsyncMock(return_value=[grant])
    monkeypatch.setattr(PagePermissionService, "effective_grants", effective)
    legacy = AsyncMock(return_value=[])
    monkeypatch.setattr(rbac, "resolve_user_permissions", legacy)
    monkeypatch.setattr(warehouse, "resolve_user_permissions", legacy)
    from app.modules.quality.api import deps as quality_deps

    monkeypatch.setattr(quality_deps, "resolve_user_permissions", legacy)
    if module == "quality":
        record = SimpleNamespace(id=uuid4())
        business = AsyncMock(return_value=record)
        monkeypatch.setattr(quality, "create_review_record", business)
        monkeypatch.setattr(quality, "get_review_files", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            quality,
            "build_review_out",
            Mock(
                return_value={
                    "id": record.id,
                    "title": "权限验证",
                    "review_mode": "upload",
                    "status": "draft",
                }
            ),
        )
    elif module == "hr":
        business = AsyncMock(return_value={"id": str(uuid4())})
        app.dependency_overrides[hr.get_training_ledger_service] = lambda: (
            SimpleNamespace(update_dept_mapping=business)
        )
    else:
        business = AsyncMock(return_value={"ok": True, "steps": []})
        app.dependency_overrides[warehouse.get_warehouse_service] = lambda: (
            SimpleNamespace(test_feishu_connectivity=business)
        )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def request():
            return await client.request(
                method,
                f"/api/v1/{module}{path}",
                headers={"X-Dazah-Page-Key": page},
                json=payload,
            )

        assert (await request()).status_code == 403
        business.assert_not_awaited()
        grant.permissions.append("operate")
        if actions:
            assert (await request()).status_code == 403
            business.assert_not_awaited()
        grant.sensitive_actions = actions
        allowed = await request()
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["code"] == 200
        business.assert_awaited_once()
        # Saved revocation must also defeat retained legacy wildcard permissions.
        legacy.return_value = ["*", f"{module}:write"]
        grant.permissions = ["access", "query"]
        assert (await request()).status_code == 403
        business.assert_awaited_once()
        legacy.assert_not_awaited()
