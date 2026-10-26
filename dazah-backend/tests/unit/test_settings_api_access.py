"""Settings administration APIs must stay closed to ordinary administrators."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.llm.api import router as llm_router
from app.modules.agent.api import router as agent_router
from app.modules.agent.audit_service import AgentAuditService
from app.modules.agent.schemas import AgentAuditSessionPage
from app.platform.audit.api import router as audit_router
from app.platform.audit.schemas import GeneralAuditLogPage
from app.platform.audit.service import GeneralAuditLogService
from app.platform.identity import deps, rbac


class _EmptyScalars:
    def all(self) -> list[Any]:
        return []


class _EmptyResult:
    def scalars(self) -> _EmptyScalars:
        return _EmptyScalars()


class _FakeDB:
    def add(self, _record: Any) -> None:
        return None

    async def execute(self, *_args: Any, **_kwargs: Any) -> _EmptyResult:
        return _EmptyResult()


async def _empty_audit_page(self: Any, _db: Any, **_kwargs: Any) -> GeneralAuditLogPage:
    return GeneralAuditLogPage(items=[], page=1, page_size=20, total=0)


async def _missing_audit_detail(self: Any, _db: Any, **_kwargs: Any) -> None:
    return None


async def _empty_session_page(
    self: Any, _db: Any, **_kwargs: Any
) -> AgentAuditSessionPage:
    return AgentAuditSessionPage(items=[], page=1, page_size=20, total=0)


async def _missing_session_detail(self: Any, _db: Any, **_kwargs: Any) -> None:
    return None


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role="admin", status="active")


@pytest.fixture
def settings_app(monkeypatch: pytest.MonkeyPatch):
    current = {"user": _admin()}
    ordinary_ids: set[uuid.UUID] = set()

    async def _is_ordinary_admin(_db: Any, user_id: Any) -> bool:
        return uuid.UUID(str(user_id)) in ordinary_ids

    monkeypatch.setattr(rbac, "is_ordinary_admin", _is_ordinary_admin)
    monkeypatch.setattr(GeneralAuditLogService, "list_logs", _empty_audit_page)
    monkeypatch.setattr(GeneralAuditLogService, "get_log", _missing_audit_detail)
    monkeypatch.setattr(AgentAuditService, "list_sessions", _empty_session_page)
    monkeypatch.setattr(
        AgentAuditService, "get_session_detail", _missing_session_detail
    )

    app = FastAPI()
    app.include_router(audit_router, prefix="/api/v1/audit")
    app.include_router(llm_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1/agent")
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[deps.get_current_user] = lambda: current["user"]
    try:
        yield app, current, ordinary_ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ordinary_administrator_cannot_read_audit_or_manage_llm(
    settings_app: tuple[FastAPI, dict[str, Any], set[uuid.UUID]],
) -> None:
    app, current, ordinary_ids = settings_app
    ordinary = _admin()
    current["user"] = ordinary
    ordinary_ids.add(ordinary.id)

    read_paths = (
        "/api/v1/audit/logs?category=business",
        f"/api/v1/audit/logs/{uuid.uuid4()}",
        "/api/v1/agent/audit/sessions?page=1&page_size=20",
        f"/api/v1/agent/audit/sessions/{uuid.uuid4()}",
        "/api/v1/llm/configs",
        "/api/v1/llm/configs?config_type=text",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in read_paths:
            response = await client.get(path)
            assert response.status_code == 403, (path, response.text)

        write_requests = (
            ("DELETE", f"/api/v1/llm/configs/{uuid.uuid4()}"),
            ("POST", "/api/v1/llm/configs/test"),
        )
        for method, path in write_requests:
            response = await client.request(method, path)
            assert response.status_code == 403, (path, response.text)


@pytest.mark.asyncio
async def test_system_administrator_keeps_audit_and_llm_access(
    settings_app: tuple[FastAPI, dict[str, Any], set[uuid.UUID]],
) -> None:
    app, current, ordinary_ids = settings_app
    assert not ordinary_ids
    assert current["user"].role == "admin"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/api/v1/audit/logs?category=business",
            "/api/v1/agent/audit/sessions?page=1&page_size=20",
            "/api/v1/llm/configs",
        ):
            response = await client.get(path)
            assert response.status_code == 200, (path, response.text)

        assert (
            await client.get(f"/api/v1/audit/logs/{uuid.uuid4()}")
        ).status_code == 404
