from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.hr import agent_tools as tools
from app.platform.identity.data_scope import DepartmentScope


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "model", "dependency", "method"),
    [
        ("list_employees", "EmployeeListInput", "EmployeeService", "list_employees"),
        (
            "list_training_records",
            "TrainingListInput",
            "TrainingLedgerService",
            "list_records",
        ),
        (
            "list_training_plans",
            "PlanListInput",
            "AnnualTrainingPlanService",
            "list_plans",
        ),
    ],
)
async def test_queries_always_forward_authorized_department_scope(
    monkeypatch,
    handler,
    model,
    dependency,
    method,
):
    actor = object()
    db = object()
    resolve = AsyncMock(
        return_value=DepartmentScope(is_all=False, department_names={"生产部"})
    )
    monkeypatch.setattr(tools, "resolve_user_department_scope", resolve)
    query = AsyncMock(return_value=([], 7))
    monkeypatch.setattr(
        tools, dependency, lambda session: SimpleNamespace(**{method: query})
    )
    result = await getattr(tools, handler)(
        SimpleNamespace(db=db, user=actor),
        getattr(tools, model)(page=2, page_size=3),
    )
    assert result == {"data": [], "meta": {"page": 2, "page_size": 3, "total": 7}}
    resolve.assert_awaited_once_with(db, actor)
    assert query.await_args.kwargs["dept_alias_set"] == {"生产部"}


@pytest.mark.asyncio
async def test_department_override_is_denied_before_query(monkeypatch):
    monkeypatch.setattr(
        tools,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"生产部"}),
        ),
    )
    with pytest.raises(HTTPException) as error:
        await tools.list_employees(
            SimpleNamespace(db=object(), user=object()),
            tools.EmployeeListInput(department="财务部"),
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_actor_is_denied():
    with pytest.raises(HTTPException) as error:
        await tools.list_training_records(
            SimpleNamespace(db=object(), user=None),
            tools.TrainingListInput(),
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_employee_response_preserves_business_fields(monkeypatch):
    employee_id = uuid4()
    employee = tools.EmployeeResponse(
        id=employee_id,
        name="测试员工",
        department="生产部",
        position="操作员",
        hire_date=date(2026, 10, 1),
    )
    monkeypatch.setattr(
        tools,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"生产部"}),
        ),
    )
    query = AsyncMock(return_value=([employee], 1))
    monkeypatch.setattr(
        tools, "EmployeeService", lambda db: SimpleNamespace(list_employees=query)
    )
    result = await tools.list_employees(
        SimpleNamespace(db=object(), user=object()),
        tools.EmployeeListInput(),
    )
    assert result["data"][0]["id"] == str(employee_id)
    assert result["data"][0]["hire_date"] == "2026-10-01"
    assert result["data"][0]["department"] == "生产部"
