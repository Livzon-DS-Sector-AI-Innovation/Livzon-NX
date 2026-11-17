from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt.api_jwt
import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from PIL import Image
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.platform.audit import middleware as audit_middleware
from app.platform.audit.models import AuditLog
from app.platform.identity import (
    api,
    impersonation,
    permission_cache,
    permission_middleware,
)
from app.platform.identity.agent_delegation import (
    issue_agent_delegation,
    require_agent_delegation,
)
from app.platform.identity.models import (
    DepartmentRoleRule,
    Role,
    User,
    UserPageGrant,
    UserRole,
)
from app.platform.identity.rbac import ORDINARY_ADMIN_ROLE_CODE
from app.platform.identity.service import generate_jwt
from app.platform.system import feedback_api
from app.platform.system.feedback_models import UserFeedback

ROOT = "/api/v1/identity"
START = f"{ROOT}/auth/impersonation/start"
EXIT = f"{ROOT}/auth/impersonation/exit"


class SwitchStore:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}
        self.unavailable = False
        self.ttl = 0

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert nx
        if key in self.sessions:
            return False
        self.sessions[key] = value
        self.ttl = ex
        return True

    async def get(self, key: str) -> str | None:
        if self.unavailable:
            raise RedisConnectionError("test outage")
        return self.sessions.get(key)

    async def eval(self, _source: str, count: int, key: str, value: str) -> None:
        assert count == 1
        if self.sessions.get(key) == value:
            self.sessions.pop(key, None)


class AuditSink:
    def __init__(self) -> None:
        self.logs: list[AuditLog] = []

    def add(self, log: AuditLog) -> None:
        self.logs.append(log)

    async def commit(self) -> None:
        pass


@pytest.fixture
async def switch_client(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DEV_BYPASS_AUTH", False)
    monkeypatch.setattr(settings, "SECRET_KEY", "simulation-test-only-" * 3)
    monkeypatch.setattr(settings, "MODULE_ACCESS_MODE", "roles")
    monkeypatch.setattr(settings, "JWT_EXPIRE_SECONDS", 120)
    store, audit = SwitchStore(), AuditSink()
    monkeypatch.setattr(impersonation, "redis_client", store)
    monkeypatch.setattr(
        permission_cache, "get_cached_permissions", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(permission_cache, "set_cached_permissions", AsyncMock())

    @asynccontextmanager
    async def shared_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    @asynccontextmanager
    async def audit_db() -> AsyncIterator[AuditSink]:
        yield audit

    monkeypatch.setattr(permission_middleware, "async_session_factory", shared_db)
    monkeypatch.setattr(audit_middleware, "async_session_factory", audit_db)
    app = FastAPI()
    app.include_router(api.auth_router, prefix=ROOT)
    app.include_router(api.user_router, prefix=ROOT)
    app.include_router(feedback_api.router, prefix="/api/v1")
    app.add_middleware(permission_middleware.PermissionMiddleware)
    app.add_middleware(audit_middleware.AuditMiddleware)

    async def request_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = request_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=settings.browser_origins[0],
        headers={"Origin": settings.browser_origins[0]},
    ) as client:
        yield client, store, audit


def user(prefix: str, role: str = "user", status: str = "active") -> User:
    return User(
        name=f"{prefix}-{uuid4().hex[:12]}",
        role=role,
        status=status,
        auth_source="local",
        tenant_key="default",
        session_version=0,
    )


@pytest.mark.anyio
async def test_effective_identity_write_audit_and_restore(
    switch_client, db_session: AsyncSession
) -> None:
    client, store, audit = switch_client
    admin, target, other = user("admin", "admin"), user("target"), user("other")
    db_session.add_all([admin, target, other])
    await db_session.flush()
    db_session.add(
        UserPageGrant(
            user_id=target.id,
            page_key="hr:employee-management:profile",
            permissions=["access", "query"],
            scope_type="department_tree",
        )
    )
    await db_session.flush()
    normal_headers = {"Authorization": f"Bearer {generate_jwt(target)}"}
    normal = (await client.get(f"{ROOT}/me", headers=normal_headers)).json()["data"]
    assert normal["id"] == str(target.id)
    assert any(
        grant["source"] == "user"
        and grant["data_scope"]["scope_type"] == "department_tree"
        for grant in normal["page_permissions"]
    )
    admin_token = generate_jwt(admin)
    client.cookies.clear()
    client.cookies.set("auth_token", admin_token)
    start = await client.post(START, json={"target_id": str(target.id)})
    assert start.status_code == 200
    assert "HttpOnly" in start.headers["Set-Cookie"]
    assert set(start.json()["data"]) == {"expires_at"}
    assert 0 < store.ttl <= 120
    switch = client.cookies.get(impersonation.COOKIE)
    assert switch
    current = await client.get(
        f"{ROOT}/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert current.status_code == 200
    assert "Set-Cookie" not in current.headers
    effective = current.json()["data"]
    assert (
        effective.pop("impersonation")["expires_at"]
        == start.json()["data"]["expires_at"]
    )
    normal.pop("impersonation")
    assert effective == normal
    nested = await client.post(START, json={"target_id": str(other.id)})
    assert nested.status_code == 409

    screenshot = BytesIO()
    Image.new("RGB", (40, 30), "white").save(screenshot, "PNG")
    feedback_id = uuid4()
    written = await client.post(
        f"{ROOT}/me/feedback",
        data={
            "feedback_id": str(feedback_id),
            "description": "验证模拟视角写入的归属和审计",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        files={"screenshots": ("test.png", screenshot.getvalue(), "image/png")},
    )
    assert written.status_code == 201, written.text
    feedback = await db_session.get(UserFeedback, feedback_id)
    assert feedback is not None and feedback.created_by == target.id
    denied = await client.patch(f"{ROOT}/admin/feedback/{feedback_id}", json={})
    assert denied.status_code == 403
    assert (await client.post(f"{ROOT}/auth/session/logout")).status_code == 409
    assert target.session_version == 0
    context = next(
        log.extra["impersonation"] for log in audit.logs if log.path == START
    )
    assert context["administrator_id"] == str(admin.id)
    assert context["target_id"] == str(target.id)
    log = next(
        log for log in audit.logs if log.request_id == written.headers["X-Request-ID"]
    )
    assert log.user_id == target.id
    assert log.status_code == 201 and log.extra["impersonation"] == context
    business_log = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "feedback_submitted",
            AuditLog.resource_id == feedback_id,
        )
    )
    assert business_log is not None and business_log.extra["impersonation"] == context

    # Either delivery path resolves the same authenticated context.
    simulation_headers = {"Authorization": f"Bearer {switch}"}
    settings = get_settings()
    request = Request({"type": "http", "headers": [], "state": {}})
    context_reset = impersonation.current_impersonation.set(None)
    try:
        await impersonation.resolve_impersonation(request, db_session, settings, switch)
        delegated = issue_agent_delegation(settings, target, source="web")
        assert (
            await require_agent_delegation(
                db_session,
                settings,
                delegated,
                user_id=target.id,
                tenant_id="default",
            )
        ).id == target.id
    finally:
        impersonation.current_impersonation.reset(context_reset)

    exited = await client.post(EXIT)
    assert exited.json()["data"] == {"administrator_restored": True}
    assert impersonation.COOKIE not in client.cookies
    assert (await client.get(f"{ROOT}/me")).json()["data"]["id"] == str(admin.id)
    assert (
        await client.get(f"{ROOT}/me", headers=simulation_headers)
    ).status_code == 401
    assert (await client.get(f"{ROOT}/me", headers=normal_headers)).status_code == 200
    assert (
        next(log for log in audit.logs if log.path == EXIT).extra["impersonation"]
        == context
    )
    with pytest.raises(HTTPException) as error:
        await require_agent_delegation(
            db_session,
            settings,
            delegated,
            user_id=target.id,
            tenant_id="default",
        )
    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_eligibility_duplicate_revocation_and_redis_outage(
    switch_client, db_session: AsyncSession
) -> None:
    client, store, _ = switch_client
    admin, ordinary = user("switch", "admin"), user("switch", "admin")
    target, disabled = user("switch"), user("switch", status="disabled")
    super_admin = user("switch", "admin")
    role = await db_session.scalar(
        select(Role).where(Role.code == ORDINARY_ADMIN_ROLE_CODE)
    )
    if role is None:
        role = Role(code=ORDINARY_ADMIN_ROLE_CODE, name="普通管理员")
        db_session.add(role)
    db_session.add_all([admin, ordinary, target, disabled, super_admin])
    await db_session.flush()
    db_session.add(UserRole(user_id=ordinary.id, role_id=role.id))
    await db_session.flush()
    ordinary_headers = {"Authorization": f"Bearer {generate_jwt(ordinary)}"}
    assert (
        await client.post(
            START, headers=ordinary_headers, json={"target_id": str(target.id)}
        )
    ).status_code == 403
    assert (
        await client.get(
            f"{ROOT}/admin/impersonation/targets", headers=ordinary_headers
        )
    ).status_code == 403
    client.cookies.clear()
    host = client.base_url.host
    client.cookies.set(
        "auth_token",
        generate_jwt(admin),
        domain=host if "." in host else f"{host}.local",
    )
    listing = await client.get(
        f"{ROOT}/admin/impersonation/targets", params={"keyword": ordinary.name}
    )
    assert [item["id"] for item in listing.json()["data"]["items"]] == [
        str(ordinary.id)
    ]
    for excluded in (admin, super_admin, disabled):
        listing = await client.get(
            f"{ROOT}/admin/impersonation/targets", params={"keyword": excluded.name}
        )
        assert listing.json()["data"] == {"items": [], "total": 0}
    assert (
        await client.post(START, json={"target_id": str(admin.id)})
    ).status_code == 422
    assert (
        await client.post(START, json={"target_id": str(super_admin.id)})
    ).status_code == 403
    assert (
        await client.post(START, json={"target_id": str(disabled.id)})
    ).status_code == 404
    assert (
        await client.post(START, json={"target_id": str(target.id)})
    ).status_code == 200
    switch = client.cookies.get(impersonation.COOKIE)
    client.cookies.delete(impersonation.COOKIE)
    assert (
        await client.post(START, json={"target_id": str(target.id)})
    ).status_code == 409
    client.cookies.set(
        impersonation.COOKIE, switch, domain=host if "." in host else f"{host}.local"
    )
    store.unavailable = True
    assert (await client.get(f"{ROOT}/me")).status_code == 503
    store.unavailable = False
    target.role = "admin"
    await db_session.flush()
    assert (await client.get(f"{ROOT}/me")).status_code == 401
    target.role = "user"
    target.status = "disabled"
    await db_session.flush()
    assert (await client.get(f"{ROOT}/me")).status_code == 401
    admin.session_version += 1
    await db_session.flush()
    assert (await client.post(EXIT)).json()["data"]["administrator_restored"] is False
    assert not store.sessions and not client.cookies.get("auth_token")


@pytest.mark.anyio
async def test_target_list_includes_distinct_manual_and_department_roles(
    switch_client, db_session: AsyncSession
) -> None:
    client, _, _ = switch_client
    prefix = uuid4().hex[:12]
    admin, assigned, unassigned = user("admin", "admin"), user(prefix), user(prefix)
    assigned.department = f"角色验收部门-{prefix}"
    manual_role = Role(name="采购查询员", code=f"reader-{prefix}")
    department_role = Role(name="供应商审核员", code=f"reviewer-{prefix}")
    db_session.add_all([admin, assigned, unassigned, manual_role, department_role])
    await db_session.flush()
    db_session.add(UserRole(user_id=assigned.id, role_id=manual_role.id))
    db_session.add_all([
        DepartmentRoleRule(department_name=assigned.department, role_id=role.id)
        for role in (manual_role, department_role)
    ])
    await db_session.flush()

    listing = await client.get(
        f"{ROOT}/admin/impersonation/targets",
        params={"keyword": prefix},
        headers={"Authorization": f"Bearer {generate_jwt(admin)}"},
    )

    assert listing.status_code == 200
    data = listing.json()["data"]
    assert data["total"] == 2
    roles_by_id = {item["id"]: item["roles"] for item in data["items"]}
    assert roles_by_id == {
        str(assigned.id): [
            {"id": str(department_role.id), "name": department_role.name},
            {"id": str(manual_role.id), "name": manual_role.name},
        ],
        str(unassigned.id): [],
    }


@pytest.mark.anyio
async def test_targets_combine_role_filter_with_search_before_pagination(
    switch_client, db_session: AsyncSession
) -> None:
    client, _, _ = switch_client
    prefix = uuid4().hex[:12]
    role = Role(name="筛选验收角色", code=f"filter-{prefix}")
    administrator = user("admin", "admin")
    manual, by_name, by_id = (user(prefix) for _ in range(3))
    unmatched = user(prefix)
    disabled = user(prefix, status="disabled")
    for index, account in enumerate((manual, by_name, by_id, unmatched, disabled)):
        account.name = f"{prefix}-{index}"
    manual.username = f"account-{prefix}"
    by_name.department = f"部门-{prefix}"
    by_id.employee_no = f"employee-{prefix}"
    by_id.feishu_department_ids = f'["dept-{prefix}"]'
    unmatched.feishu_department_ids = f'["dept-{prefix}-other"]'
    manual.feishu_department_ids = "invalid legacy data"
    db_session.add_all(
        [role, administrator, manual, by_name, by_id, unmatched, disabled]
    )
    await db_session.flush()
    db_session.add_all(
        [
            UserRole(user_id=manual.id, role_id=role.id),
            UserRole(user_id=disabled.id, role_id=role.id),
            DepartmentRoleRule(department_name=by_name.department, role_id=role.id),
            DepartmentRoleRule(feishu_department_id=f"dept-{prefix}", role_id=role.id),
        ]
    )
    await db_session.flush()
    url = f"{ROOT}/admin/impersonation/targets"
    headers = {"Authorization": f"Bearer {generate_jwt(administrator)}"}
    filters = {"role_id": str(role.id), "keyword": prefix}

    response = await client.get(url, headers=headers, params={**filters, "limit": 2})
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 3
    assert [row["id"] for row in response.json()["data"]["items"]] == [
        str(manual.id),
        str(by_name.id),
    ]
    page_two = await client.get(
        url, headers=headers, params={**filters, "limit": 2, "offset": 2}
    )
    assert page_two.json()["data"]["total"] == 3
    assert [row["id"] for row in page_two.json()["data"]["items"]] == [str(by_id.id)]
    for keyword, account in (
        (manual.username, manual),
        (by_name.name, by_name),
        (by_id.employee_no, by_id),
    ):
        search = await client.get(
            url, headers=headers, params={**filters, "keyword": keyword}
        )
        assert search.json()["data"]["total"] == 1
        assert search.json()["data"]["items"][0]["id"] == str(account.id)
    no_match = await client.get(
        url, headers=headers, params={**filters, "keyword": unmatched.name}
    )
    assert no_match.json()["data"] == {"items": [], "total": 0}
    invalid = await client.get(url, headers=headers, params={"role_id": "not-a-uuid"})
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_expired_switch_requires_explicit_return(
    switch_client,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = switch_client
    admin, target = user("expiry", "admin"), user("expiry")
    db_session.add_all([admin, target])
    await db_session.flush()
    client.cookies.set("auth_token", generate_jwt(admin))
    monkeypatch.setattr(impersonation, "DURATION", timedelta(seconds=5))
    started = await client.post(START, json={"target_id": str(target.id)})
    assert started.status_code == 200
    advanced = datetime.now(UTC) + timedelta(seconds=6)

    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return advanced.astimezone(tz)

    monkeypatch.setattr(jwt.api_jwt, "datetime", FutureClock)
    assert (await client.get(f"{ROOT}/me")).status_code == 401
    assert (await client.post(EXIT)).json()["data"]["administrator_restored"] is True
    assert impersonation.COOKIE not in client.cookies
