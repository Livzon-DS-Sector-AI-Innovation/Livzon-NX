"""RBAC 权限系统测试：目录、路径匹配、权限解析、中间件 401/403。"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI, Header, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.platform.identity.models import (
    DepartmentRoleRule,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.platform.identity.rbac import (
    PERMISSION_MODULES,
    SUPER_ADMIN_ROLE_CODE,
    build_permission_catalog,
    is_identity_read_only,
    is_public_path,
    match_action,
    match_module,
    resolve_user_permissions,
    resolve_user_roles,
    seed_permissions,
)
from app.platform.identity.repository import RbacRepository

TEST_USER_ID = "00000000-0000-0000-0000-0000000000aa"


# ─── 权限目录 ────────────────────────────────────────────────────────


def test_catalog_count() -> None:
    catalog = build_permission_catalog()
    # 16 模块 x 2 + identity:admin + 仓储细分编辑 3（product/hardware/raw:write）
    # + HR 员工档案细分 1（employee:read）
    # + 质量子域编辑 6（qc/product_qa/change_qa/validation_qa/
    #   system_qa/material_qa:write）= 43
    assert len(catalog) == 43
    codes = {c["code"] for c in catalog}
    assert "hr:read" in codes and "hr:write" in codes
    assert "identity:admin" in codes
    assert "quality:read" in codes
    assert "quality:qc:write" in codes
    assert "quality:system_qa:write" in codes
    # 仓储细分编辑权限（按飞书部门映射的子领域）
    for scope_code in (
        "warehouse:product:write",
        "warehouse:hardware:write",
        "warehouse:raw:write",
    ):
        assert scope_code in codes
    # HR 员工档案页面细分权限（仅人力资源部可见）
    assert "hr:employee:read" in codes
    for module in PERMISSION_MODULES:
        assert f"{module}:read" in codes


# ─── 路径匹配 ────────────────────────────────────────────────────────


def test_match_module() -> None:
    cases = [
        ("/api/v1/hr/employees", "hr"),
        ("/api/v1/quality/deviations", "quality"),
        ("/api/v1/regulatory-tracker/summary", "regulatory_tracker"),
        ("/api/v1/regulatory-documents/sync/status", "regulatory_tracker"),
        ("/api/v1/sync-jobs", "regulatory_tracker"),
        ("/api/v1/llm/configs", "llm"),
        ("/api/v1/identity/me", "identity"),
        ("/api/v1/identity/admin/roles", "identity"),
        ("/api/v1/identity/sync/members", "identity"),
        ("/api/v1/production/batches", "production"),
        ("/api/v1/warehouse/raw-summary", "warehouse"),
    ]
    for path, expected in cases:
        assert match_module(path) == expected, f"{path} -> {expected}"


def test_match_action() -> None:
    assert match_action("GET") == "read"
    assert match_action("HEAD") == "read"
    assert match_action("POST") == "write"
    assert match_action("PUT") == "write"
    assert match_action("DELETE") == "write"


def test_is_public_path() -> None:
    assert is_public_path("/health")
    assert is_public_path("/docs")
    assert is_public_path("/openapi.json")
    assert is_public_path("/api/v1/identity/auth/login")
    assert is_public_path("/api/v1/identity/auth/callback")
    assert is_public_path("/mcp")
    assert is_public_path("/uploads/x.png")
    assert not is_public_path("/api/v1/hr/employees")


def test_identity_read_only() -> None:
    assert is_identity_read_only("/api/v1/identity/me")
    assert is_identity_read_only("/api/v1/identity/departments")
    assert is_identity_read_only("/api/v1/identity/personnel")
    assert not is_identity_read_only("/api/v1/identity/sync/members")
    assert not is_identity_read_only("/api/v1/identity/admin/roles")


# ─── 权限解析（部门映射 + 手动并集）──────────────────────────────────


async def _setup_rbac_data(db) -> None:
    """创建测试用户 + 质量/HR 角色 + 部门规则 + 手动分配。"""
    await seed_permissions(db)
    repo = RbacRepository()

    user = User(
        id=TEST_USER_ID,
        name="测试用户",
        feishu_open_id="test-open-id-aa",
        department="质量管理部",
        feishu_department_ids=json.dumps(["od-test-qa"]),
    )
    db.add(user)
    await db.flush()

    qa_role = await repo.get_role_by_code(db, "test_qa_role")
    if qa_role is None:
        qa_role = await repo.create_role(db, name="质量审核员", code="test_qa_role")
    hr_role = await repo.get_role_by_code(db, "test_hr_role")
    if hr_role is None:
        hr_role = await repo.create_role(db, name="HR专员", code="test_hr_role")

    perms = await repo.list_permissions(db)
    quality_perms = [p for p in perms if p.module == "quality"]
    await repo.set_role_permissions(db, qa_role.id, [p.id for p in quality_perms])
    hr_read = [p for p in perms if p.code == "hr:read"]
    await repo.set_role_permissions(db, hr_role.id, [p.id for p in hr_read])

    await repo.create_dept_rule(
        db, role_id=qa_role.id, feishu_department_id="od-test-qa"
    )
    await repo.assign_user_role(db, TEST_USER_ID, hr_role.id)
    await db.flush()


async def _cleanup_user(db, user_id) -> None:
    """清理指定用户的 RBAC 数据（角色绑定 + 用户 + 缓存）。"""
    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    from app.platform.identity.permission_cache import invalidate_permissions

    await invalidate_permissions(user_id)
    await db.flush()


async def _cleanup_rbac_data(db) -> None:
    await _cleanup_user(db, TEST_USER_ID)
    await db.execute(
        delete(DepartmentRoleRule).where(
            DepartmentRoleRule.feishu_department_id == "od-test-qa"
        )
    )
    for code in ("test_qa_role", "test_hr_role"):
        await db.execute(delete(Role).where(Role.code == code))
    await db.flush()


@pytest.mark.asyncio
async def test_resolve_union_dedup(db_session) -> None:
    await _setup_rbac_data(db_session)
    try:
        roles = await resolve_user_roles(db_session, TEST_USER_ID)
        codes = {r.code for r in roles}
        assert codes == {"test_qa_role", "test_hr_role"}, f"并集去重失败: {codes}"

        permissions = await resolve_user_permissions(db_session, TEST_USER_ID)
        permission_set = set(permissions)
        assert "quality:read" in permission_set
        assert "quality:write" in permission_set
        assert "hr:read" in permission_set
        assert "hr:write" not in permission_set
    finally:
        await _cleanup_rbac_data(db_session)


@pytest.mark.asyncio
async def test_resolve_super_admin_wildcard(db_session) -> None:
    await _setup_rbac_data(db_session)
    try:
        repo = RbacRepository()
        super_role = await repo.get_role_by_code(db_session, SUPER_ADMIN_ROLE_CODE)
        await repo.assign_user_role(db_session, TEST_USER_ID, super_role.id)
        await db_session.flush()

        permissions = await resolve_user_permissions(db_session, TEST_USER_ID)
        assert permissions == ["*"], f"super_admin 通配失败: {permissions}"
    finally:
        await _cleanup_rbac_data(db_session)


@pytest.mark.asyncio
async def test_resolve_department_name_fallback(db_session) -> None:
    """无 feishu_department_ids 时按部门名退化匹配。"""
    await seed_permissions(db_session)
    repo = RbacRepository()
    qa_role = await repo.get_role_by_code(db_session, "test_qa_role")
    if qa_role is None:
        qa_role = await repo.create_role(
            db_session, name="质量审核员", code="test_qa_role"
        )
    await repo.create_dept_rule(
        db_session, role_id=qa_role.id, department_name="质量管理部"
    )

    user = User(
        id=TEST_USER_ID,
        name="测试用户",
        feishu_open_id="test-open-id-ab",
        department="质量管理部",
        feishu_department_ids=None,
    )
    db_session.add(user)
    await db_session.flush()
    try:
        roles = await resolve_user_roles(db_session, TEST_USER_ID)
        assert {r.code for r in roles} == {"test_qa_role"}
    finally:
        await _cleanup_rbac_data(db_session)


# ─── 冻结用户拦截 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skip(reason="当前认证服务不再暴露迁移前的 _check_user_frozen 包装函数")
async def test_frozen_user_rejected(db_session, monkeypatch) -> None:
    """HR 状态非在职 + 飞书实时确认冻结 → 拒绝登录。"""
    from app.platform.identity.service import _check_user_frozen

    # mock 飞书实时确认：is_frozen=True
    async def _fake_frozen(*args, **kwargs):
        return (["od-frozen"], "冻结部门", True)

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_user_department_ids",
        _fake_frozen,
    )

    user = User(
        id=TEST_USER_ID,
        name="冻结用户",
        feishu_open_id="test-open-id-frozen",
    )
    db_session.add(user)
    await db_session.flush()

    from app.modules.hr.models import HrFeishuMember

    member = HrFeishuMember(
        open_id="test-open-id-frozen",
        name="冻结用户",
        status="4",  # 冻结
    )
    db_session.add(member)
    await db_session.flush()
    try:
        assert await _check_user_frozen(db_session, user) is True
    finally:
        await _cleanup_user(db_session, TEST_USER_ID)
        await db_session.execute(
            __import__("sqlalchemy")
            .delete(HrFeishuMember)
            .where(HrFeishuMember.open_id == "test-open-id-frozen")
        )
        await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.skip(reason="当前认证服务不再暴露迁移前的 _check_user_frozen 包装函数")
async def test_hr_nonactive_but_feishu_active_allowed(db_session, monkeypatch) -> None:
    """HR 状态非在职但飞书实时确认未冻结 → 放行（防误伤）。"""
    from app.platform.identity.service import _check_user_frozen

    # mock 飞书实时确认：is_frozen=False（HR 表数据滞后/不准）
    async def _fake_active(*args, **kwargs):
        return (["od-qa"], "质量管理部", False)

    monkeypatch.setattr(
        "app.platform.integrations.feishu.contact.get_user_department_ids",
        _fake_active,
    )

    user = User(
        id=TEST_USER_ID,
        name="疑似冻结用户",
        feishu_open_id="test-open-id-flag",
    )
    db_session.add(user)
    await db_session.flush()

    from app.modules.hr.models import HrFeishuMember

    member = HrFeishuMember(
        open_id="test-open-id-flag",
        name="疑似冻结用户",
        status="4",  # HR 表标记冻结，但飞书确认在职
    )
    db_session.add(member)
    await db_session.flush()
    try:
        assert await _check_user_frozen(db_session, user) is False
    finally:
        await _cleanup_user(db_session, TEST_USER_ID)
        await db_session.execute(
            __import__("sqlalchemy")
            .delete(HrFeishuMember)
            .where(HrFeishuMember.open_id == "test-open-id-flag")
        )
        await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.skip(reason="当前认证服务不再暴露迁移前的 _check_user_frozen 包装函数")
async def test_active_user_allowed(db_session) -> None:
    """HR 同步状态在职（'1'）的用户允许登录。"""
    from app.platform.identity.service import _check_user_frozen

    user = User(
        id=TEST_USER_ID,
        name="在职用户",
        feishu_open_id="test-open-id-active",
    )
    db_session.add(user)
    await db_session.flush()

    from app.modules.hr.models import HrFeishuMember

    member = HrFeishuMember(
        open_id="test-open-id-active",
        name="在职用户",
        status="1",  # 在职
    )
    db_session.add(member)
    await db_session.flush()
    try:
        assert await _check_user_frozen(db_session, user) is False
    finally:
        await _cleanup_user(db_session, TEST_USER_ID)
        await db_session.execute(
            __import__("sqlalchemy")
            .delete(HrFeishuMember)
            .where(HrFeishuMember.open_id == "test-open-id-active")
        )
        await db_session.flush()


# ─── 中间件 401/403（关闭 DEV_BYPASS_AUTH 的独立 app）────────────────


@pytest.fixture
def _strict_app(monkeypatch):
    """构造 DEV_BYPASS_AUTH=False 的测试 app + NullPool 会话工厂。

    返回 (test_app, session_factory)：中间件使用同一 NullPool 工厂，
    避免全局连接池跨事件循环导致 "Event loop is closed"。
    """
    from sqlalchemy import pool
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.core.config import Settings, get_settings
    from app.platform.identity.permission_middleware import PermissionMiddleware

    strict_settings = Settings(
        APP_ENV="test",
        DEV_BYPASS_AUTH=False,
        MODULE_ACCESS_MODE="roles",
        SECRET_KEY="test-secret-key",
        DATABASE_URL=get_settings().DATABASE_URL,
    )
    monkeypatch.setattr(
        "app.platform.identity.permission_middleware.get_settings",
        lambda: strict_settings,
    )

    test_engine = create_async_engine(
        get_settings().DATABASE_URL,
        poolclass=pool.NullPool,
    )
    test_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.platform.identity.permission_middleware.async_session_factory",
        test_factory,
    )

    test_app = FastAPI()
    test_app.add_middleware(PermissionMiddleware)

    @test_app.get("/api/v1/hr/employees")
    async def hr_employees():
        return {"ok": True}

    @test_app.get("/api/v1/identity/me")
    async def identity_me():
        return {"ok": True}

    @test_app.get("/api/v1/identity/admin/roles")
    async def admin_roles():
        return {"ok": True}

    @test_app.get("/api/v1/identity/auth/login")
    async def auth_login():
        return {"ok": True}

    @test_app.post("/api/v1/warehouse/material-pages/x/records/y")
    async def warehouse_record_write():
        return {"ok": True}

    @test_app.get("/api/v1/agent/llm/models")
    async def agent_llm_models(authorization: str | None = Header(default=None)):
        if authorization != "Bearer service-token":
            raise HTTPException(status_code=401, detail="service token required")
        return {"ok": True}

    return test_app, test_factory


def _make_jwt(
    open_id: str, secret: str, user_id: str = TEST_USER_ID, exp_offset: int = 3600
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "open_id": open_id,
        "name": "测试用户",
        "iat": now,
        "exp": now + timedelta(seconds=exp_offset),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.asyncio
async def test_middleware_401_without_token(_strict_app) -> None:
    test_app, _ = _strict_app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/hr/employees")
        assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_middleware_public_auth_path(_strict_app) -> None:
    test_app, _ = _strict_app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/identity/auth/login")
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_middleware_allows_agent_service_token_route_to_validate_at_endpoint(
    _strict_app,
) -> None:
    test_app, _ = _strict_app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/agent/llm/models",
            headers={"Authorization": "Bearer service-token"},
        )
        missing = await ac.get("/api/v1/agent/llm/models")

    assert resp.status_code == 200, resp.text
    assert missing.status_code == 401, missing.text


@pytest.mark.asyncio
async def test_middleware_403_without_permission(_strict_app) -> None:
    test_app, session_factory = _strict_app

    user_id = uuid4()
    try:
        async with session_factory() as db:
            user = User(
                id=user_id,
                name="无权限用户",
                feishu_open_id="test-open-id-ac",
            )
            db.add(user)
            await db.commit()

        token = _make_jwt("test-open-id-ac", "test-secret-key", user_id=str(user_id))
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/hr/employees",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            role_result = await db.execute(
                select(Role).where(Role.code == "read_only_role")
            )
            for role in role_result.scalars().all():
                await db.execute(
                    delete(RolePermission).where(RolePermission.role_id == role.id)
                )
                await db.execute(delete(UserRole).where(UserRole.role_id == role.id))
                await db.execute(delete(Role).where(Role.id == role.id))
            await db.commit()


@pytest.mark.asyncio
async def test_middleware_200_with_permission(_strict_app) -> None:
    test_app, session_factory = _strict_app

    user_id = uuid4()
    try:
        async with session_factory() as db:
            await seed_permissions(db)
            repo = RbacRepository()
            user = User(
                id=user_id,
                name="有权限用户",
                feishu_open_id="test-open-id-ad",
            )
            db.add(user)
            await db.flush()
            super_role = await repo.get_role_by_code(db, SUPER_ADMIN_ROLE_CODE)
            await repo.assign_user_role(db, user_id, super_role.id)
            await db.commit()

        token = _make_jwt("test-open-id-ad", "test-secret-key", user_id=str(user_id))
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/hr/employees",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            await db.commit()


@pytest.mark.asyncio
async def test_middleware_write_passthrough_with_subscope_permission(
    _strict_app,
) -> None:
    """仓储细分写码（module:resource:write）放行模块级写校验（端点内精校验）。"""
    test_app, session_factory = _strict_app
    user_id = uuid4()
    try:
        async with session_factory() as db:
            await seed_permissions(db)
            repo = RbacRepository()
            user = User(
                id=user_id,
                name="仓储成品管理员用户",
                feishu_open_id="test-open-id-subscope",
            )
            db.add(user)
            await db.flush()
            role = Role(
                name="仓储成品管理员",
                code="wh_product_admin_test",
                is_system=False,
            )
            db.add(role)
            await db.flush()
            perm = (
                await db.execute(
                    select(Permission).where(
                        Permission.code == "warehouse:product:write"
                    )
                )
            ).scalar_one()
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            await repo.assign_user_role(db, user_id, role.id)
            await db.commit()

        token = _make_jwt(
            "test-open-id-subscope", "test-secret-key", user_id=str(user_id)
        )
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 路由存在；细分写权限通过模块级中间件后由端点继续处理。
            resp = await ac.post(
                "/api/v1/warehouse/material-pages/x/records/y",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            role_result = await db.execute(
                select(Role).where(Role.code == "wh_product_admin_test")
            )
            for role in role_result.scalars().all():
                await db.execute(
                    delete(RolePermission).where(RolePermission.role_id == role.id)
                )
                await db.execute(delete(UserRole).where(UserRole.role_id == role.id))
                await db.execute(delete(Role).where(Role.id == role.id))
            await db.commit()


@pytest.mark.asyncio
async def test_middleware_write_403_without_any_write_permission(_strict_app) -> None:
    """仅有 read 无任何写码 → 写请求 403。"""
    test_app, session_factory = _strict_app
    user_id = uuid4()
    try:
        async with session_factory() as db:
            await seed_permissions(db)
            repo = RbacRepository()
            user = User(
                id=user_id,
                name="只读用户",
                feishu_open_id="test-open-id-readonly",
            )
            db.add(user)
            await db.flush()
            role = Role(name="只读角色", code="read_only_role", is_system=False)
            db.add(role)
            await db.flush()
            perm = (
                await db.execute(
                    select(Permission).where(Permission.code == "warehouse:read")
                )
            ).scalar_one()
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            await repo.assign_user_role(db, user_id, role.id)
            await db.commit()

        token = _make_jwt(
            "test-open-id-readonly", "test-secret-key", user_id=str(user_id)
        )
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/warehouse/material-pages/x/records/y",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            await db.commit()
