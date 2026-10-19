"""Production page grants must govern all equivalent write entry points."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.modules.production import extraction_report_api, pressure_api
from app.modules.production.pressure_schemas import (
    BatchAuditResponse,
    OcrSubmitResponse,
)
from app.platform.identity import rbac
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import get_page_definition
from tests.modules.production.test_page_permission_acceptance import acceptance_app


@pytest.mark.asyncio
@pytest.mark.parametrize("task_entry", [False, True])
@pytest.mark.parametrize("actions,expected", [([], 403), (["bulk_import"], 200)])
async def test_both_ocr_entry_points_require_bulk_import(
    monkeypatch,
    task_entry,
    actions,
    expected,
):
    app, _ = acceptance_app(
        pressure_api.router,
        monkeypatch,
        "production:pressure",
        actions=actions,
    )
    creating = AsyncMock(return_value=OcrSubmitResponse(success_count=2))
    submitting = AsyncMock(return_value=OcrSubmitResponse(success_count=2))
    app.dependency_overrides[pressure_api.get_pressure_service] = lambda: (
        SimpleNamespace(
            create_ocr_records=creating,
            submit_ocr_task_result=submitting,
        )
    )
    path = f"/ocr-tasks/{uuid4()}/submit" if task_entry else "/records/ocr"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/pressure" + path,
            headers={"X-Dazah-Page-Key": "production:pressure"},
            json={
                "image_url": "https://example.invalid/ocr.png",
                "records": [
                    {"point_id": "test-1", "pressure_value": 1},
                    {"point_id": "test-2", "pressure_value": 2},
                ],
            },
        )
    assert response.status_code == expected, response.text
    called = submitting if task_entry else creating
    if expected == 200:
        called.assert_awaited_once()
        assert response.json()["data"]["success_count"] == 2
    else:
        called.assert_not_awaited()


def test_pressure_reject_is_an_independent_page_action():
    page = get_page_definition("production:pressure")
    assert page is not None
    assert {"approve", "reject"}.issubset(
        {action.key for action in page.sensitive_actions}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize(
    "decision,required", [("approved", "approve"), ("rejected", "reject")]
)
@pytest.mark.parametrize(
    "actions", [[], ["approve"], ["reject"], ["approve", "reject"]]
)
async def test_pressure_decisions_require_the_matching_action(
    monkeypatch,
    batch,
    decision,
    required,
    actions,
):
    app, _ = acceptance_app(
        pressure_api.router,
        monkeypatch,
        "production:pressure",
        actions=actions,
    )
    auditing = AsyncMock(return_value={"success": True})
    batch_audit = AsyncMock(return_value=BatchAuditResponse(success_count=1))
    app.dependency_overrides[pressure_api.get_pressure_service] = lambda: (
        SimpleNamespace(
            audit_record=auditing,
            batch_audit=batch_audit,
        )
    )
    record_id = str(uuid4())
    path = "/batch-audit" if batch else f"/{record_id}/audit"
    payload = {"status": decision, "reject_reason": "测试驳回原因"}
    if batch:
        payload["ids"] = [record_id]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/v1/production/pressure/records" + path,
            headers={"X-Dazah-Page-Key": "production:pressure"},
            json=payload,
        )
    expected = 200 if required in actions else 403
    assert response.status_code == expected, response.text
    called = batch_audit if batch else auditing
    if expected == 200:
        called.assert_awaited_once()
        body = called.await_args.args[0 if batch else 1]
        assert body.status == decision
    else:
        auditing.assert_not_awaited()
        batch_audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("decision", [None, "unknown", True, {}, ["approved"]])
async def test_pressure_invalid_decision_never_reaches_service(
    monkeypatch, batch, decision
):
    app, _ = acceptance_app(
        pressure_api.router,
        monkeypatch,
        "production:pressure",
        actions=["approve", "reject"],
    )
    service = SimpleNamespace(audit_record=AsyncMock(), batch_audit=AsyncMock())
    app.dependency_overrides[pressure_api.get_pressure_service] = lambda: service
    path = "/batch-audit" if batch else f"/{uuid4()}/audit"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/v1/production/pressure/records" + path,
            headers={"X-Dazah-Page-Key": "production:pressure"},
            json={"status": decision},
        )
    assert response.status_code == 422, response.text
    service.audit_record.assert_not_awaited()
    service.batch_audit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("legacy", [[], ["production:extraction-yield"], ["*"]])
@pytest.mark.parametrize(
    "scope,expected",
    [
        ("all", 200),
        ("production_extraction", 200),
        ("production_fermentation", 403),
    ],
)
async def test_daily_report_uses_page_scope_without_legacy_permissions(
    monkeypatch,
    method,
    legacy,
    scope,
    expected,
):
    app, db = acceptance_app(
        extraction_report_api.router,
        monkeypatch,
        "production:overview",
        scope_type=scope,
    )
    legacy_check = AsyncMock(return_value=legacy)
    monkeypatch.setattr(rbac, "resolve_user_permissions", legacy_check)
    item = SimpleNamespace(id=uuid4(), report_date=date(2026, 10, 16), quantity_kg=1)
    db.execute = AsyncMock(
        return_value=Mock(
            scalars=Mock(return_value=Mock(all=Mock(return_value=[item]))),
            scalar_one_or_none=Mock(return_value=item),
        )
    )
    db.refresh = AsyncMock()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/production/extraction-daily-reports?product=FA",
            headers={"X-Dazah-Page-Key": "production:overview"},
            **(
                {"json": {"report_date": "2026-10-16", "quantity_kg": 2}}
                if method == "POST"
                else {}
            ),
        )
    assert response.status_code == expected, response.text
    legacy_check.assert_not_awaited()
    if expected == 403:
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()
    elif method == "POST":
        db.commit.assert_awaited_once()
        assert response.json()["data"]["quantity_kg"] == 2
    else:
        assert response.json()["data"][0]["quantity_kg"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("explicit_product", [False, True])
async def test_daily_report_hidden_product_is_denied_even_when_defaulted(
    monkeypatch,
    method,
    explicit_product,
):
    app, db = acceptance_app(
        extraction_report_api.router,
        monkeypatch,
        "production:overview",
        scope_type="production_extraction",
        visible_sections=["MC"],
    )
    monkeypatch.setattr(rbac, "resolve_user_permissions", AsyncMock(return_value=["*"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/production/extraction-daily-reports"
            + ("?product=FA" if explicit_product else ""),
            headers={"X-Dazah-Page-Key": "production:overview"},
            **(
                {"json": {"report_date": "2026-10-16", "quantity_kg": 2}}
                if method == "POST"
                else {}
            ),
        )
    assert response.status_code == 403
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_report_read_only_grant_cannot_write(monkeypatch):
    app, db = acceptance_app(
        extraction_report_api.router,
        monkeypatch,
        "production:overview",
        scope_type="all",
    )
    grants = PagePermissionService.effective_grants.return_value
    grants[0].permissions = ["access", "query"]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/production/extraction-daily-reports",
            headers={"X-Dazah-Page-Key": "production:overview"},
            json={"report_date": "2026-10-16", "quantity_kg": 2},
        )
    assert response.status_code == 403
    db.commit.assert_not_awaited()
