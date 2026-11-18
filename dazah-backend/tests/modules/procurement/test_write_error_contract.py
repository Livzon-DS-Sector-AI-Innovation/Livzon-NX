from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.modules.procurement import api, service


@pytest.fixture
async def procurement_http():
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(api.router, prefix="/api/v1/procurement")
    test_app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.parametrize("resource", ["suppliers", "purchase-requests"])
async def test_import_reports_bad_workbook_and_common_http_errors(
    procurement_http, monkeypatch, resource
) -> None:
    path = f"/api/v1/procurement/{resource}/import"
    malformed = await procurement_http.post(
        path, files={"file": ("bad.xlsx", b"invalid")}
    )
    assert malformed.status_code == malformed.json()["code"] == 422
    assert malformed.json()["detail"] == {
        "error_code": "PROCUREMENT_IMPORT_TABLE_INVALID",
    }
    wrong_type = await procurement_http.post(
        path, files={"file": ("bad.pdf", b"invalid")}
    )
    assert wrong_type.status_code == wrong_type.json()["code"] == 415
    assert "detail" not in wrong_type.json()
    monkeypatch.setattr(api, "MAX_INVOICE_PDF_UPLOAD_BYTES", 1)
    too_large = await procurement_http.post(
        path, files={"file": ("file.xlsx", b"more")}
    )
    assert too_large.status_code == too_large.json()["code"] == 413

    published = app.openapi()["paths"][path]["post"]["responses"]["422"]
    assert published["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProcurementErrorResponse",
    }


async def test_purchase_workflow_separates_conflict_missing_and_correctable_data(
    procurement_http, monkeypatch
) -> None:
    path = f"/api/v1/procurement/purchase-requests/{uuid4()}"
    request = SimpleNamespace(status="draft", category="hardware")
    repo = SimpleNamespace(
        get=AsyncMock(return_value=request),
        get_for_update=AsyncMock(return_value=request),
        list_items=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(service, "PurchaseRequestRepository", lambda _: repo)
    submit = await procurement_http.post(f"{path}/submit")
    assert submit.status_code == submit.json()["code"] == 422
    assert submit.json()["detail"] == {"error_code": "PROCUREMENT_SUBMIT_ITEMS_MISSING"}
    repo.list_items.return_value = [
        SimpleNamespace(
            sequence=1,
            quantity=Decimal("2"),
            unit_price=Decimal("3"),
            total_amount=Decimal("0"),
        )
    ]
    mismatched = await procurement_http.post(f"{path}/submit")
    assert mismatched.status_code == mismatched.json()["code"] == 422
    assert mismatched.json()["detail"] == {
        "error_code": "PROCUREMENT_SUBMIT_AMOUNT_MISMATCH"
    }
    approval = {
        "approval_role": "department_head",
        "approver_name": "测试审批人",
        "result": "approved",
    }
    conflict = await procurement_http.post(f"{path}/approve", json=approval)
    assert conflict.status_code == conflict.json()["code"] == 409
    assert "detail" not in conflict.json()
    repo.get_for_update.return_value = None
    missing = await procurement_http.post(
        f"{path}/reject", json={**approval, "result": "rejected"}
    )
    assert missing.status_code == missing.json()["code"] == 404
    assert "detail" not in missing.json()
