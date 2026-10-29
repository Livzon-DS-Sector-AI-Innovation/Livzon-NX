"""HR employee updates reject arbitrary persistence attributes."""

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
from app.modules.hr.schemas import EmployeeUpdate
from app.modules.hr.service import EmployeeService
from app.platform.identity.deps import get_current_user


@pytest.mark.parametrize(
    "field", ["id", "is_deleted", "created_by", "updated_by", "feishu_record_id"]
)
def test_employee_update_rejects_system_fields(field):
    with pytest.raises(ValidationError) as error:
        EmployeeUpdate.model_validate({"name": "test", field: "injected"})
    assert any(item["type"] == "extra_forbidden" for item in error.value.errors())


def test_employee_update_preserves_declared_business_fields():
    update = EmployeeUpdate(
        name="test",
        department="quality",
        phone="123",
        sub_department="lab",
        work_experience_1="example",
    )
    assert update.model_dump(exclude_unset=True) == {
        "name": "test",
        "department": "quality",
        "phone": "123",
        "sub_department": "lab",
        "work_experience_1": "example",
    }


@pytest.mark.parametrize("body", [{"is_deleted": True}, {"created_by": str(uuid4())}])
async def test_employee_api_rejects_system_fields_before_writes(monkeypatch, body):
    service = SimpleNamespace(update_employee=AsyncMock())
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_employee_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(f"/employees/{uuid4()}", json=body)
    assert response.status_code == 422
    service.update_employee.assert_not_awaited()


async def test_employee_service_filters_extra_attributes():
    employee = SimpleNamespace(
        name="before", department="quality", sub_department="lab", is_deleted=False
    )
    service = EmployeeService.__new__(EmployeeService)
    service.get_employee = AsyncMock(return_value=employee)
    service.repo = SimpleNamespace(update=AsyncMock(return_value=employee))
    service._assert_employee_scope = AsyncMock()
    service._sync_single_to_feishu = AsyncMock()
    data = EmployeeUpdate(name="after")
    object.__setattr__(data, "__pydantic_extra__", {"is_deleted": True})
    await service.update_employee(uuid4(), data)
    assert employee.name == "after"
    assert employee.is_deleted is False
    service.repo.update.assert_awaited_once_with(employee)


async def test_employee_api_accepts_declared_form_fields(monkeypatch):
    employee = SimpleNamespace(
        id=uuid4(),
        name="after",
        employee_number="audit-user",
        department="quality",
        position="analyst",
        hire_date=date(2026, 1, 1),
    )
    service = SimpleNamespace(
        session=None, update_employee=AsyncMock(return_value=employee)
    )
    monkeypatch.setattr(api, "_assert_employee_page_access", AsyncMock())
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_employee_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            f"/employees/{employee.id}",
            json={
                "name": "after",
                "sub_department": "lab",
                "work_experience_1": "test",
            },
        )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "after"
    payload = service.update_employee.await_args.args[1]
    assert payload.sub_department == "lab"
    assert payload.work_experience_1 == "test"
