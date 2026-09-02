import json
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.procurement.api import router
from app.modules.procurement.models import PurchaseRequest
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import Department
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import page_key_for_route
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.anyio
async def test_request_list_detail_create_and_update_share_page_scope(
    db_session, monkeypatch
):
    suffix = uuid4().hex[:10]
    own_name, outside_name = f"允许部门-{suffix}", f"其他部门-{suffix}"
    own_id = f"od-{suffix}"
    db_session.add(Department(feishu_department_id=own_id, name=own_name))
    own = PurchaseRequest(
        category="office",
        request_department=own_name,
        request_date=date.today(),
        status="draft",
    )
    other = PurchaseRequest(
        category="office",
        request_department=outside_name,
        request_date=date.today(),
        status="draft",
    )
    db_session.add_all([own, other])
    await db_session.flush()
    user = SimpleNamespace(
        id=uuid4(),
        name="可信经办人",
        department=own_name,
        feishu_department_ids=json.dumps([own_id]),
    )
    page_key = page_key_for_route("/purchasing/request/office")

    async def rollout(*args, **kwargs):
        return SimpleNamespace(status="enforced")

    async def grants(*args, **kwargs):
        return [
            EffectivePageGrantOut(
                page_key=page_key,
                module_code="procurement",
                permissions=["access", "query", "operate"],
                sensitive_actions=["delete", "bulk_import"],
                data_scope=PageDataScopeInput(
                    scope_type="departments", department_ids=[own_id]
                ),
                source="user",
            )
        ]

    monkeypatch.setattr(PagePermissionRepository, "get_rollout", rollout)
    monkeypatch.setattr(PagePermissionService, "effective_grants", grants)
    app = FastAPI()
    app.include_router(
        router,
        prefix="/api/v1/procurement",
        dependencies=[Depends(require_module_view("procurement"))],
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    headers = {"X-Dazah-Page-Key": page_key}
    base = "/api/v1/procurement/purchase-requests"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        response = await client.get(base)
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["data"]} == {str(own.id)}
        assert response.json()["meta"]["total"] == 1
        assert (await client.get(f"{base}/{own.id}")).status_code == 200
        for method in ("GET", "PUT", "DELETE"):
            response = await client.request(
                method, f"{base}/{other.id}", json={} if method == "PUT" else None
            )
            assert response.status_code == 403
        response = await client.put(
            f"{base}/{own.id}", json={"request_department": outside_name}
        )
        assert response.status_code == 403
        assert own.request_department == own_name
        response = await client.put(
            f"{base}/{own.id}", json={"attachment_note": "允许修改"}
        )
        assert response.status_code == 200
        assert own.attachment_note == "允许修改"
        assert (
            await client.get(base, params={"category": "hardware"})
        ).status_code == 403
        response = await client.post(
            base,
            json={
                "category": "office",
                "request_department": outside_name,
                "request_date": date.today().isoformat(),
                "items": [{"product_name": "办公纸", "quantity": 1, "unit_price": 2}],
            },
        )
        assert response.status_code == 403
