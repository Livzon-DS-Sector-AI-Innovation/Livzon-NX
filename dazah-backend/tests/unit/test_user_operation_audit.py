import uuid
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from starlette.responses import JSONResponse

from app.platform.audit import middleware as audit_middleware
from app.platform.audit import retention
from app.platform.audit.middleware import OPERATION_ACTION, AuditMiddleware
from app.platform.audit.models import AuditLog
from app.platform.audit.service import (
    GeneralAuditLogService,
    _category_filter,
    audit_category_of,
)
from app.platform.identity import permission_cache, permission_middleware
from app.platform.identity.models import User
from app.platform.identity.repository import UserRepository


class FakeSession:
    def __init__(self, *, fail: bool = False) -> None:
        self.records: list[AuditLog] = []
        self.fail = fail

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def add(self, record: AuditLog) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        if self.fail:
            raise RuntimeError("audit storage unavailable")


@pytest.mark.asyncio
async def test_user_api_requests_record_one_safe_row_each(monkeypatch: Any) -> None:
    actor_id = uuid.uuid4()
    session = FakeSession()
    monkeypatch.setattr(audit_middleware, "async_session_factory", lambda: session)
    app = FastAPI()

    @app.get("/api/v1/quality/items/{item_id}", summary="查看质量记录")
    async def read_item(request: Request, item_id: str) -> JSONResponse:
        request.state.audit_user_id = actor_id
        return JSONResponse({"id": item_id})

    @app.post("/api/v1/quality/items/{item_id}", summary="修改质量记录")
    async def write_item(request: Request, item_id: str) -> JSONResponse:
        request.state.audit_user_id = actor_id
        return JSONResponse({"id": item_id}, status_code=403)

    @app.post("/api/v1/identity/auth/local/login", summary="本地账号登录")
    async def login(request: Request) -> JSONResponse:
        request.state.audit_user_id = actor_id
        return JSONResponse({"ok": True})

    @app.post("/api/v1/identity/auth/session/logout", summary="撤销当前用户会话")
    async def logout(request: Request) -> JSONResponse:
        request.state.audit_user_id = actor_id
        return JSONResponse({"ok": True})

    @app.get("/api/v1/quality/public", summary="未认证查询")
    async def anonymous() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/health", summary="健康检查")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True})

    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/api/v1/quality/items/secret-id?token=secret")
        await client.post(
            "/api/v1/quality/items/secret-id", json={"password": "secret"}
        )
        await client.post("/api/v1/identity/auth/local/login")
        await client.post("/api/v1/identity/auth/session/logout")
        await client.get("/api/v1/quality/public")
        await client.get("/health")

    assert len(session.records) == 4
    assert [row.status_code for row in session.records] == [200, 403, 200, 200]
    assert {row.user_id for row in session.records} == {actor_id}
    assert all(row.action == OPERATION_ACTION for row in session.records)
    assert session.records[0].resource_type == "quality"
    assert session.records[0].path == "/api/v1/quality/items/{item_id}"
    assert session.records[0].extra == {"operation": "查看质量记录"}
    assert session.records[2].resource_type == "identity"
    assert "secret" not in str([row.__dict__ for row in session.records])


@pytest.mark.asyncio
async def test_audit_storage_failure_preserves_api_result(monkeypatch: Any) -> None:
    session = FakeSession(fail=True)
    monkeypatch.setattr(audit_middleware, "async_session_factory", lambda: session)
    app = FastAPI()

    @app.get("/api/v1/audit/logs", summary="查询审计")
    async def list_logs(request: Request) -> JSONResponse:
        request.state.audit_user_id = uuid.uuid4()
        return JSONResponse({"ok": True})

    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/audit/logs")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(session.records) == 1


@pytest.mark.asyncio
async def test_verified_permission_denial_is_recorded(monkeypatch: Any) -> None:
    actor_id = uuid.uuid4()
    user = User(
        id=actor_id,
        name="测试用户",
        role="user",
        status="active",
        auth_source="local",
        session_version=0,
    )
    audit_session = FakeSession()
    monkeypatch.setattr(
        audit_middleware, "async_session_factory", lambda: audit_session
    )
    monkeypatch.setattr(permission_middleware, "async_session_factory", FakeSession)
    monkeypatch.setattr(
        permission_middleware,
        "get_settings",
        lambda: SimpleNamespace(
            browser_origins=[],
            DEV_BYPASS_AUTH=False,
            SECRET_KEY="test-only-key",
            effective_module_access_mode="roles",
        ),
    )

    async def get_by_id(_self: Any, _db: Any, _user_id: str) -> User:
        return user

    async def no_permissions(_user_id: str) -> list[str]:
        return []

    monkeypatch.setattr(UserRepository, "get_by_id", get_by_id)
    monkeypatch.setattr(permission_cache, "get_cached_permissions", no_permissions)
    app = FastAPI()

    @app.get("/api/v1/quality/items", summary="查看质量记录")
    async def list_items() -> JSONResponse:
        return JSONResponse({"ok": True})

    app.add_middleware(permission_middleware.PermissionMiddleware)
    app.add_middleware(AuditMiddleware)
    token = jwt.encode(
        {"sub": str(actor_id), "session_version": 0}, "test-only-key", algorithm="HS256"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/quality/items", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403
    assert len(audit_session.records) == 1
    assert audit_session.records[0].user_id == actor_id
    assert audit_session.records[0].status_code == 403


def test_operation_category_is_exclusive() -> None:
    record = AuditLog(action=OPERATION_ACTION, resource_type="quality")
    assert audit_category_of(record) == "operations"
    operation_sql = str(
        select(AuditLog.id)
        .where(_category_filter("operations"))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    business_sql = str(
        select(AuditLog.id)
        .where(_category_filter("business"))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "action = 'platform_api_request'" in operation_sql
    assert "action != 'platform_api_request'" in business_sql


@pytest.mark.asyncio
async def test_operation_list_filters_module_and_operation_name() -> None:
    statements: list[Any] = []

    class QuerySession:
        async def scalar(self, statement: Any) -> int:
            statements.append(statement)
            return 0

        async def execute(self, statement: Any) -> Any:
            statements.append(statement)
            return SimpleNamespace(all=lambda: [])

    page = await GeneralAuditLogService().list_logs(
        QuerySession(),
        category="operations",
        page=1,
        page_size=20,
        module="quality",
        keyword="查看质量记录",
    )
    assert page.total == 0
    sql = str(
        statements[1].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "audit.logs.resource_type = 'quality'" in sql
    assert "operation" in sql
    assert "查看质量记录" in sql


@pytest.mark.asyncio
async def test_retention_deletes_only_expired_operation_ids(monkeypatch: Any) -> None:
    expired_id = uuid.uuid4()
    statements: list[Any] = []

    class RetentionSession(FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def scalars(self, statement: Any) -> Any:
            statements.append(statement)
            self.calls += 1
            return SimpleNamespace(all=lambda: [expired_id] if self.calls == 1 else [])

        async def execute(self, statement: Any) -> None:
            statements.append(statement)

    session = RetentionSession()
    monkeypatch.setattr(retention, "async_session_factory", lambda: session)
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(USER_OPERATION_AUDIT_RETENTION_DAYS=30),
    )
    assert await retention.purge_expired_user_operations() == 1
    query = statements[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    assert "platform_api_request" in str(query)
    assert "created_at <" in str(query)
    assert "LIMIT 1000" in str(query)
    assert "WHERE audit.logs.id IN" in str(statements[1])
