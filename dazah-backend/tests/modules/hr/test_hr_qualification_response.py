"""Historical qualification text must not make HR read endpoints return 500."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.database import get_db
from app.modules.hr import api
from app.modules.hr.schemas import EmployeeResponse, OffboardingRecordResponse
from app.platform.identity.deps import get_current_user

LONG_QUALIFICATION = "测试职业资格及技能证书说明；" * 6


def _employee(qualification: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name="测试员工",
        department="测试部门",
        position="测试岗位",
        hire_date=date(2026, 1, 1),
        qualification_type=qualification,
    )


@pytest.fixture
def read_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Isolate storage and authorization facts; use real routes and serializers.
    # No database or external service is contacted by this regression suite.
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/hr")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="admin", status="active"
    )
    monkeypatch.setattr(api, "_resolve_visible_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_assert_dept_in_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_assert_employee_page_access", AsyncMock())
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["employees", "offboarding-records"])
@pytest.mark.parametrize(
    "qualification", [None, "工程师", "职" * 32, "职" * 33, LONG_QUALIFICATION]
)
async def test_hr_lists_and_details_preserve_qualification_text(
    read_app: FastAPI, qualification: str | None, path: str
) -> None:
    employee = _employee(qualification)
    record = SimpleNamespace(
        id=uuid4(),
        name="测试员工",
        qualification_type=qualification,
        employee=employee,
    )
    employees = SimpleNamespace(
        list_employees=AsyncMock(return_value=([employee], 1)),
        get_employee=AsyncMock(return_value=employee),
        session=None,
    )
    offboarding = SimpleNamespace(
        list_records=AsyncMock(return_value=([record], 1)),
        get_record=AsyncMock(return_value=record),
    )
    read_app.dependency_overrides[api.get_employee_service] = lambda: employees
    read_app.dependency_overrides[api.get_offboarding_service] = lambda: offboarding
    async with AsyncClient(
        transport=ASGITransport(app=read_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/hr/{path}")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["qualification_type"] == qualification
        if path == "offboarding-records":
            nested = body["data"][0]["employee"]
            assert nested["qualification_type"] == qualification
        record_id = record.id if path == "offboarding-records" else employee.id
        detail = await client.get(f"/api/v1/hr/{path}/{record_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["qualification_type"] == qualification


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["employees", "offboarding-records"])
@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_hr_writes_still_reject_overlength_qualification(
    read_app: FastAPI, path: str, method: str
) -> None:
    create = AsyncMock()
    update = AsyncMock()
    service = SimpleNamespace(
        create_employee=create,
        create_record=create,
        update_employee=update,
        update_record=update,
    )
    read_app.dependency_overrides[api.get_employee_service] = lambda: service
    read_app.dependency_overrides[api.get_offboarding_service] = lambda: service
    url = f"/api/v1/hr/{path}"
    if method == "PUT":
        url += f"/{uuid4()}"
    payload = {"qualification_type": "职" * 33}
    if method == "POST" and path == "employees":
        payload.update(
            name="测试员工",
            department="测试部门",
            position="测试岗位",
            hire_date="2026-01-01",
        )
    async with AsyncClient(
        transport=ASGITransport(app=read_app), base_url="http://test"
    ) as client:
        response = await client.request(method, url, json=payload)
    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "qualification_type"]
        and error["type"] == "string_too_long"
        for error in response.json()["detail"]
    )
    create.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.parametrize("schema", [EmployeeResponse, OffboardingRecordResponse])
def test_response_qualification_still_requires_text(schema: type) -> None:
    payload = vars(_employee(None))
    payload["qualification_type"] = ["工程师"]
    with pytest.raises(ValidationError, match="qualification_type"):
        schema.model_validate(payload)
