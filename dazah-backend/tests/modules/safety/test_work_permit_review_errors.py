from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.deps import get_current_user
from app.main import app
from app.modules.safety.api import work_permits as api
from app.modules.safety.service import work_permit as service


@pytest.fixture
async def review_http(monkeypatch):
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(api.work_permits_router)
    user = SimpleNamespace(id=uuid4(), role="user")
    db = SimpleNamespace(commit=AsyncMock())
    now = datetime.now(UTC)
    permit = SimpleNamespace(
        id=uuid4(),
        created_by=user.id,
        status="draft",
        permit_type="hot_work",
        permit_level="level1",
        permit_no="WP-0001",
        type_data={},
        persons=[],
        safety_measures=[],
        risk_identifications=[],
        planned_start_time=now,
        planned_end_time=now + timedelta(hours=1),
        approval_round=0,
        current_node_seq=0,
    )
    state = SimpleNamespace(user=user, permit=permit, db=db)
    test_app.dependency_overrides[get_db] = lambda: db
    test_app.dependency_overrides[get_current_user] = lambda: state.user
    monkeypatch.setattr(service, "_lock_permit", AsyncMock(return_value=permit))
    monkeypatch.setattr(service, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "cache_set", AsyncMock())
    monkeypatch.setattr(service, "cache_delete", AsyncMock())
    monkeypatch.setattr(api, "notify_after_transition", AsyncMock())
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client, f"/work-permits/{permit.id}", state


@pytest.mark.parametrize("transition", ["approve", "reject"])
async def test_review_not_current_state_uses_409_and_auth_expiry_uses_401(
    review_http, transition
):
    client, url, state = review_http
    url = f"{url}/nodes/{uuid4()}/{transition}"
    response = await client.post(url, json={"opinion": "安全措施不足"})
    assert response.status_code == 409
    assert "detail" not in response.json()

    state.user = None
    response = await client.post(url, json={"opinion": "安全措施不足"})
    assert response.status_code == 401
    assert "detail" not in response.json()
    state.db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("reason", "error_code"),
    [
        ("time", "SAFETY_WORK_PERMIT_TIME_INVALID"),
        ("certificate", "SAFETY_WORK_PERMIT_CERTIFICATE_INVALID"),
        ("approver", "SAFETY_WORK_PERMIT_APPROVER_REQUIRED"),
    ],
)
async def test_submit_returns_only_codes_with_different_corrections(
    review_http, monkeypatch, reason, error_code
):
    client, url, state = review_http
    monkeypatch.setattr(service, "validate_permit_payload", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        service,
        "_load_settings",
        AsyncMock(return_value={"cert_check_strict": reason == "certificate"}),
    )
    monkeypatch.setattr(
        service, "certificate_check_issues", AsyncMock(return_value=["证件无效"])
    )
    monkeypatch.setattr(service, "_validity_hours", AsyncMock(return_value=8.0))
    monkeypatch.setattr(service, "_approver_config_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        service,
        "active_nodes_for_level",
        lambda *_: [
            {"key": "leader", "name": "车间负责人", "kind": service.NODE_KIND_APPROVE}
        ],
    )
    if reason == "time":
        state.permit.planned_end_time = None
    response = await client.post(f"{url}/submit", json={"assignments": []})
    assert response.status_code == 422
    assert response.json()["detail"] == {"error_code": error_code}
    state.db.commit.assert_not_awaited()
    service.cache_delete.assert_awaited_once()


async def test_duplicate_submit_and_permission_denial_do_not_add_codes(review_http):
    client, url, state = review_http
    state.permit.created_by = uuid4()
    response = await client.post(f"{url}/submit", json={"assignments": []})
    assert response.status_code == 403
    assert "detail" not in response.json()

    service.cache_get.return_value = "1"
    response = await client.post(f"{url}/submit", json={"assignments": []})
    assert response.status_code == 423
    assert "detail" not in response.json()
    state.db.commit.assert_not_awaited()


async def test_submit_success_preserves_nonblocking_certificate_warning(
    review_http, monkeypatch
):
    client, url, state = review_http
    monkeypatch.setattr(
        service,
        "submit_permit",
        AsyncMock(return_value=(state.permit, ["证件即将到期"])),
    )
    response = await client.post(f"{url}/submit", json={"assignments": []})
    assert response.status_code == 200
    assert response.json()["data"]["warnings"] == ["证件即将到期"]
    state.db.commit.assert_awaited_once()
