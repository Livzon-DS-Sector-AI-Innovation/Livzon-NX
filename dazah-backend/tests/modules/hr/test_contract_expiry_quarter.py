from contextlib import asynccontextmanager
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import database, jobs
from app.core.deps import get_current_user
from app.modules.hr import api, service


@pytest.mark.parametrize(
    ("today", "start", "end"),
    [
        (datetime(2024, 2, 29), date(2024, 1, 1), date(2024, 3, 31)),
        (datetime(2026, 4, 1), date(2026, 4, 1), date(2026, 6, 30)),
        (datetime(2026, 9, 30), date(2026, 7, 1), date(2026, 9, 30)),
        (datetime(2026, 10, 8), date(2026, 10, 1), date(2026, 12, 31)),
        (datetime(2026, 12, 31), date(2026, 10, 1), date(2026, 12, 31)),
        (datetime(2027, 1, 1), date(2027, 1, 1), date(2027, 3, 31)),
    ],
)
async def test_push_endpoint_uses_current_calendar_quarter(
    monkeypatch: pytest.MonkeyPatch, today: datetime, start: date, end: date
) -> None:
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return today

    @asynccontextmanager
    async def session():
        yield object()

    employee_service = SimpleNamespace(
        list_contract_expiring=AsyncMock(return_value=([], 0))
    )
    results = []

    async def submit(callback, **kwargs):
        assert kwargs == {"task_id": "hr:push:contract-expiring-notify", "ttl": 600}
        results.append(await callback())

    monkeypatch.setattr(api, "datetime", Clock)
    monkeypatch.setattr(database, "async_session_factory", session)
    monkeypatch.setattr(service, "EmployeeService", lambda _session: employee_service)
    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(jobs, "submit_job", submit)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/hr")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/hr/employees/contract-expiring/push-notify", json={}
        )

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "running"
    employee_service.list_contract_expiring.assert_awaited_once_with(
        start_date=start, end_date=end, page=1, page_size=200
    )
    assert results[0]["total_expiring"] == 0


async def test_push_endpoint_reuses_existing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submit = AsyncMock()
    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=True))
    monkeypatch.setattr(jobs, "submit_job", submit)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/hr")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/hr/employees/contract-expiring/push-notify", json={}
        )
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "running"
    submit.assert_not_awaited()
