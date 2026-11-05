import re
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient, Response
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import get_db
from app.platform.audit import middleware
from app.platform.audit.middleware import AuditMiddleware
from app.platform.audit.models import AuditLog
from app.platform.audit.service import record_audit_log
from app.platform.identity.permission_middleware import PermissionMiddleware


class AuditSession:
    def __init__(self) -> None:
        self.records: list[AuditLog] = []

    async def __aenter__(self) -> "AuditSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def add(self, record: AuditLog) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None


@pytest.fixture
def audit_session(monkeypatch: pytest.MonkeyPatch) -> AuditSession:
    session = AuditSession()
    monkeypatch.setattr(middleware, "async_session_factory", lambda: session)
    return session


async def _request(
    method: str,
    path: str,
    *,
    status: int = 200,
    identified: bool = True,
    disposition: str | None = None,
    required: bool = False,
) -> tuple[Response, uuid.UUID]:
    actor = uuid.uuid4()
    app = FastAPI()

    @app.api_route(path, methods=[method])
    async def endpoint(request: Request) -> JSONResponse:
        if identified:
            request.state.audit_user_id = actor
        if required:
            request.state.audit_required = True
        return JSONResponse(
            {"ok": status < 400},
            status_code=status,
            headers={"Content-Disposition": disposition} if disposition else {},
        )

    app.add_middleware(AuditMiddleware)
    url = re.sub(r"\{[^}]+\}", "record-123", path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, url)
    assert response.status_code == status
    if method != "HEAD":
        assert response.json() == {"ok": status < 400}
    assert response.headers["X-Request-ID"]
    return response, actor


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/identity/me"),
        ("HEAD", "/api/v1/identity/me"),
        ("OPTIONS", "/api/v1/quality/items"),
        ("GET", "/api/v1/identity/menus"),
        ("GET", "/api/v1/quality/items/{item_id}"),
        ("GET", "/api/v1/audit/logs"),
        ("GET", "/api/v1/agent/automations/runs/{run_id}"),
        ("GET", "/api/v1/warehouse/feishu/ws/status"),
        ("GET", "/api/v1/quality/items/{item_id}/attachments/{file_token}/thumbnail"),
        ("POST", "/api/v1/warehouse/analytics/query"),
        ("POST", "/api/v1/identity/admin/permission-simulate"),
        ("POST", "/api/v1/identity/admin/page-permissions/simulate"),
    ],
)
async def test_ordinary_reads_do_not_open_an_audit_session(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    factory = Mock(side_effect=AssertionError("ordinary reads must not write audit"))
    monkeypatch.setattr(middleware, "async_session_factory", factory)
    await _request(method, path)
    factory.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("status", [200, 400, 409, 422, 500])
async def test_unclassified_writes_keep_the_audit_fallback(
    audit_session: AuditSession, method: str, status: int
) -> None:
    _, actor = await _request(
        method, "/api/v1/quality/new-feature/preview", status=status
    )
    assert len(audit_session.records) == 1
    row = audit_session.records[0]
    assert row.method == method
    assert row.status_code == status
    assert row.user_id == actor


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/hr/training-ledgers/export-by-dept",
        "/api/v1/hr/new-employee-training/plans/{plan_id}/export-confirmation",
        "/api/v1/registration/reference-standards/{record_id}/download",
        "/api/v1/hr/candidates/{record_id}/resume-file",
        "/api/v1/quality/records/{record_id}/attachments/{file_token}/content",
        "/api/v1/quality/records/{record_id}/attachments/{file_token}/preview",
        "/api/v1/warehouse/page-data/{page}/records/{id}/attachments/{file_token}",
        "/api/v1/audit/logs/{log_id}",
        "/api/v1/identity/users/{user_id}/module-permissions",
        "/api/v1/identity/users/{user_id}/livzon-access-scope",
        "/api/v1/identity/users/{user_id}/permission-audit",
        "/api/v1/hr/candidates/sync-from-feishu",
        "/api/v1/hr/plan-tracking/period",
        "/api/v1/hr/hr-settings/reminders",
        "/api/v1/hr/hr-settings/push-templates",
        "/api/v1/hr/hr-settings/push-recipients",
        "/api/v1/hr/hr-settings/hr-members",
        "/api/v1/production/mc/lineage/ai-analysis",
        "/api/v1/production/mc/lineage/ai-analysis-stream",
        "/api/v1/production/fa/lineage/ai-analysis",
        "/api/v1/production/fa/lineage/ai-analysis-stream",
        "/api/v1/production/fa/dashboard/batch-params",
    ],
)
async def test_critical_get_requests_are_preserved(
    audit_session: AuditSession, path: str
) -> None:
    await _request("GET", path)
    assert len(audit_session.records) == 1
    assert audit_session.records[0].path == path


async def test_download_response_is_audited_even_with_an_unusual_route_name(
    audit_session: AuditSession,
) -> None:
    await _request(
        "GET",
        "/api/v1/quality/generated-result",
        disposition='attachment; filename="x"',
    )
    assert len(audit_session.records) == 1


async def test_module_can_require_audit_for_a_sensitive_read(
    audit_session: AuditSession,
) -> None:
    await _request("GET", "/api/v1/hr/sensitive-view", required=True)
    assert len(audit_session.records) == 1


@pytest.mark.parametrize("status", [401, 403, 429])
@pytest.mark.parametrize("identified", [True, False])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/identity/me"),
        ("POST", "/api/v1/warehouse/analytics/query"),
    ],
)
async def test_security_denials_override_read_exclusions(
    audit_session: AuditSession,
    status: int,
    identified: bool,
    method: str,
    path: str,
) -> None:
    _, actor = await _request(method, path, status=status, identified=identified)
    assert len(audit_session.records) == 1
    row = audit_session.records[0]
    assert row.status_code == status
    assert row.user_id == (actor if identified else None)
    assert row.extra["audit_reason"] == "security"


@pytest.mark.parametrize("status", [302, 400, 500])
async def test_unidentified_sso_callback_results_are_preserved(
    audit_session: AuditSession, status: int
) -> None:
    await _request(
        "GET", "/api/v1/identity/auth/callback", status=status, identified=False
    )
    assert len(audit_session.records) == 1
    assert audit_session.records[0].user_id is None
    assert audit_session.records[0].extra["request"]["parameters_omitted"]


async def test_public_business_callback_is_preserved(
    audit_session: AuditSession,
) -> None:
    await _request("GET", "/api/v1/hr/contracts/approval-callback", identified=False)
    assert len(audit_session.records) == 1


@pytest.mark.parametrize("failure", ["password", "rate_limit", "validation"])
async def test_real_login_failures_are_audited_without_credentials_or_false_actor(
    audit_session: AuditSession, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from app.platform.identity import permission_middleware, service
    from app.platform.identity.api import auth_router

    async def fake_db() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(
        permission_middleware,
        "check_local_account_rate_limit",
        AsyncMock(return_value=failure != "rate_limit"),
    )
    authenticate = AsyncMock(side_effect=HTTPException(401, "Invalid credentials"))
    monkeypatch.setattr(service, "authenticate_local_user", authenticate)
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/identity")
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_local_login_mode="enabled", is_production=False
    )
    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/identity/auth/local/login?token=private-query",
            json={} if failure == "validation" else {
                "username": "private-account", "password": "private-password"
            },
        )
    assert response.status_code == {
        "password": 401, "rate_limit": 429, "validation": 422
    }[failure]
    assert len(audit_session.records) == 1
    row = audit_session.records[0]
    assert row.user_id is None
    assert row.ip_address == "127.0.0.1"
    assert "private-" not in str(row.extra)
    assert row.extra["request"]["parameters_omitted"] == "sensitive_route"


async def test_explicit_business_audit_survives_suppressed_request_logging(
    audit_session: AuditSession,
) -> None:
    app = FastAPI()

    @app.get("/api/v1/quality/items")
    async def endpoint(request: Request) -> dict[str, bool]:
        request.state.audit_user_id = uuid.uuid4()
        await record_audit_log(
            audit_session, action="sensitive_read", resource_type="quality"
        )
        return {"ok": True}

    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/quality/items")
    assert response.status_code == 200
    assert len(audit_session.records) == 1
    assert audit_session.records[0].action == "sensitive_read"
    assert audit_session.records[0].request_id == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("method", "path", "headers", "expected_status"),
    [
        ("GET", "/api/v1/quality/items", {}, 401),
        ("GET", "/api/v1/quality/items", {"Authorization": "Bearer invalid"}, 401),
        ("POST", "/api/v1/quality/items", {"Origin": "https://foreign.test"}, 403),
        ("POST", "/api/v1/identity/auth/local/login", {}, 429),
    ],
)
async def test_security_rejections_before_endpoint_dispatch_are_audited(
    audit_session: AuditSession,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    from app.platform.identity import permission_middleware

    settings = SimpleNamespace(
        browser_origins=["https://factory.test"],
        DEV_BYPASS_AUTH=False,
        SECRET_KEY="synthetic-test-signing-key-32-bytes",
    )
    monkeypatch.setattr(permission_middleware, "get_settings", lambda: settings)
    monkeypatch.setattr(
        permission_middleware, "_check_login_rate_limit", AsyncMock(return_value=False)
    )
    endpoint_called = Mock()
    app = FastAPI()

    @app.api_route(path, methods=[method])
    async def endpoint() -> dict[str, bool]:
        endpoint_called()
        return {"ok": True}

    app.add_middleware(PermissionMiddleware)
    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, headers=headers)
    assert response.status_code == expected_status
    endpoint_called.assert_not_called()
    assert len(audit_session.records) == 1
    assert audit_session.records[0].user_id is None
    assert audit_session.records[0].status_code == expected_status
    assert audit_session.records[0].extra["audit_reason"] == "security"


async def test_unhandled_write_failure_keeps_audit_evidence(
    audit_session: AuditSession,
) -> None:
    actor = uuid.uuid4()
    app = FastAPI()

    @app.post("/api/v1/quality/items")
    async def endpoint(request: Request) -> None:
        request.state.audit_user_id = actor
        raise RuntimeError("synthetic write failure")

    app.add_middleware(AuditMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/quality/items")
    assert response.status_code == 500
    assert len(audit_session.records) == 1
    assert audit_session.records[0].user_id == actor
    assert audit_session.records[0].status_code == 500
