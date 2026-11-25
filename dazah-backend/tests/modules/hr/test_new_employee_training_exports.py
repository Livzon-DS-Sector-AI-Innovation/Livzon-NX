from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import error_response
from app.modules.hr import api, new_employee_training_api
from app.platform.identity.deps import get_current_user


@pytest.fixture
def training_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/hr")
    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_db] = lambda: None

    @app.exception_handler(AppException)
    async def handle_app_error(request: Request, exc: AppException) -> JSONResponse:
        return error_response(
            message=exc.message, detail=exc.detail_msg, status_code=exc.status_code
        )

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "export_name", ["onboarding-training-record", "prejob-training-plan"]
)
async def test_retired_employee_training_exports_return_404(
    training_app: FastAPI, export_name: str
) -> None:
    get_employee = AsyncMock(return_value=SimpleNamespace(employee_number="E001"))
    training_app.dependency_overrides[api.get_employee_service] = lambda: (
        SimpleNamespace(get_employee=get_employee)
    )
    async with AsyncClient(
        transport=ASGITransport(app=training_app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/hr/employees/{UUID(int=1)}/{export_name}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    get_employee.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_employee_training_exports_app14(training_app: FastAPI) -> None:
    plan_id = UUID(int=1)
    get_plan = AsyncMock(
        return_value={
            "employee_name": "测试员工",
            "employee_number": "E001",
            "department": "质量部",
            "position": "质量员",
            "hire_date": "2026-08-20",
            "items": [{"textbook_name": "质量基础", "textbook_code": "SMP-01"}],
        }
    )
    service = SimpleNamespace(get_plan=get_plan)
    overrides = training_app.dependency_overrides
    overrides[new_employee_training_api._get_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=training_app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/hr/new-employee-training/plans/{plan_id}/export-confirmation"
        )

    get_plan.assert_awaited_once_with(plan_id)
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename*=UTF-8''")
    assert unquote(disposition.split("''", 1)[1]) == "岗位培训确认表_测试员工_E001.xlsx"
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    try:
        sheet = workbook.active
        assert sheet is not None
        assert sheet["D5"].value == "测试员工"
        assert sheet["B9"].value == "质量基础（SMP-01）"
    finally:
        workbook.close()
