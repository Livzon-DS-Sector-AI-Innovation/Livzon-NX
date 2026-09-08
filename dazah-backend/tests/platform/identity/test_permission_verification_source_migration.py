"""权限验证台测试：账号权限预览 / 接口准入模拟 / 权限清单导出 / admin 前缀 403。"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import Settings, get_settings
from app.platform.identity.models import (
    DataScopeRule,
    DepartmentRoleRule,
    Menu,
    Role,
    RoleMenu,
    User,
    UserRole,
)
from app.platform.identity.rbac import (
    SUPER_ADMIN_ROLE_CODE,
    resolve_user_roles,
    seed_permissions,
)
from app.platform.identity.repository import RbacRepository

TEST_USER_ID = "00000000-0000-0000-0000-0000000000bb"

# 根目录 .env.local 默认 DEV_BYPASS_AUTH=false；预览菜单组装逻辑依赖该开关，
# 测试统一用非绕过配置，走普通用户/超管的真实判定分支。
TEST_SETTINGS = Settings(
    APP_ENV="test",
    DEV_BYPASS_AUTH=False,
    SECRET_KEY="test-secret-key",
    DATABASE_URL=get_settings().DATABASE_URL,
)


@pytest.fixture(autouse=True)
def _no_external_cache(monkeypatch):
    """权限/数据范围缓存视为未命中、写入视为空操作，避免依赖外部 Redis。"""

    from app.platform.identity import permission_cache

    async def _cache_get(key: str):
        return None

    async def _cache_set(key: str, value: str, ex: int = 3600) -> None:
        return None

    async def _cache_delete(key: str) -> None:
        return None

    monkeypatch.setattr(permission_cache, "cache_get", _cache_get)
    monkeypatch.setattr(permission_cache, "cache_set", _cache_set)
    monkeypatch.setattr(permission_cache, "cache_delete", _cache_delete)


async def _setup_user(db, *, user_id=TEST_USER_ID, dept_scope=False):
    """创建测试用户：manual 角色（quality/hr/warehouse read）+ 部门映射角色。

    返回 (user, role_manual, role_dept, menu_bound, menu_unbound)。
    """
    await seed_permissions(db)
    repo = RbacRepository()

    dept_name = f"权限验证测试部-{uuid4().hex[:8]}"
    feishu_dept_id = f"od-pv-{uuid4().hex[:8]}"
    user = User(
        id=user_id,
        name="权限验证测试用户",
        feishu_open_id=f"pv-open-{uuid4().hex[:8]}",
        department=dept_name,
        feishu_department_ids=json.dumps([feishu_dept_id]),
    )
    db.add(user)
    await db.flush()

    role_manual = Role(name="权限验证手动角色", code="pv_manual_role", is_system=False)
    role_dept = Role(name="权限验证部门角色", code="pv_dept_role", is_system=False)
    db.add_all([role_manual, role_dept])
    await db.flush()

    perms = await repo.list_permissions(db)
    manual_perm_ids = [
        p.id for p in perms if p.code in ("quality:read", "hr:read", "warehouse:read")
    ]
    dept_perm_ids = [p.id for p in perms if p.code == "quality:read"]
    await repo.set_role_permissions(db, role_manual.id, manual_perm_ids)
    await repo.set_role_permissions(db, role_dept.id, dept_perm_ids)

    # 部门映射角色：按飞书部门 ID 精确匹配
    db.add(
        DepartmentRoleRule(
            role_id=role_dept.id,
            feishu_department_id=feishu_dept_id,
        )
    )
    db.add(UserRole(user_id=user.id, role_id=role_manual.id, source="manual"))
    await db.flush()

    # 菜单：一个绑定到 manual 角色，一个不绑定
    menu_bound = Menu(
        name="权限验证菜单一",
        type="menu",
        route_path="/pv/menu-one",
        status="active",
    )
    menu_unbound = Menu(
        name="权限验证菜单二",
        type="menu",
        route_path="/pv/menu-two",
        status="active",
    )
    db.add_all([menu_bound, menu_unbound])
    await db.flush()
    db.add(RoleMenu(role_id=role_manual.id, menu_id=menu_bound.id))

    # 数据范围：用户级配置指定部门
    db.add(
        DataScopeRule(
            user_id=user.id,
            scope_type="departments",
            department_names=json.dumps(["质量管理部"], ensure_ascii=False),
        )
    )
    await db.flush()

    if dept_scope:
        from app.modules.hr.models import HrUserDeptScope

        db.add(HrUserDeptScope(user_id=user.id, visible_depts=["质量管理部"]))
        await db.flush()

    return user, role_manual, role_dept, menu_bound, menu_unbound


async def _cleanup_user(db, user_id) -> None:
    from app.modules.hr.models import HrUserDeptScope
    from app.platform.identity.permission_cache import invalidate_permissions

    await db.execute(delete(HrUserDeptScope).where(HrUserDeptScope.user_id == user_id))
    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await invalidate_permissions(user_id)
    await db.flush()


# ─── 账号权限预览 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permission_preview_full_snapshot(db_session) -> None:
    from app.platform.identity.rbac_api import get_user_permission_preview

    user, role_manual, role_dept, menu_bound, menu_unbound = await _setup_user(
        db_session
    )
    try:
        resp = await get_user_permission_preview(
            user_id=str(user.id),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]

        # roles：当前预览契约返回角色基本信息
        assert data["user_id"] == str(user.id)
        role_by_code = {r["code"]: r for r in data["roles"]}
        assert set(role_by_code) == {"pv_manual_role", "pv_dept_role"}
        assert role_by_code["pv_manual_role"]["name"] == "权限验证手动角色"

        # permissions：三个 read 权限点
        assert {"quality:read", "hr:read", "warehouse:read"} <= set(data["permissions"])

        # current contract returns resolved menu IDs rather than menu payloads
        assert data["menu_ids"] == [str(menu_bound.id)]

        # data_scope：用户级配置生效
        assert data["data_scope"] == {
            "is_all": False,
            "department_names": ["质量管理部"],
        }

    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_preview_super_admin_marked(db_session) -> None:
    from app.platform.identity.rbac_api import get_user_permission_preview

    user, role_manual, role_dept, menu_bound, menu_unbound = await _setup_user(
        db_session
    )
    try:
        repo = RbacRepository()
        super_role = await repo.get_role_by_code(db_session, SUPER_ADMIN_ROLE_CODE)
        db_session.add(
            UserRole(user_id=user.id, role_id=super_role.id, source="manual")
        )
        await db_session.flush()

        resp = await get_user_permission_preview(
            user_id=str(user.id),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        super_items = [r for r in data["roles"] if r["code"] == SUPER_ADMIN_ROLE_CODE]
        assert len(super_items) == 1
        # 超管通配权限
        assert data["permissions"] == ["*"]
        # 当前菜单解析结果至少包含用户已绑定的菜单
        assert str(menu_bound.id) in data["menu_ids"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_preview_user_not_found(db_session) -> None:
    from fastapi import HTTPException

    from app.platform.identity.rbac_api import get_user_permission_preview

    with pytest.raises(HTTPException) as exc_info:
        await get_user_permission_preview(
            user_id=str(uuid4()),
            current_user=None,
            db=db_session,
        )
    assert exc_info.value.status_code == 404


# ─── 接口准入模拟 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permission_simulate_allowed(db_session) -> None:
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="GET",
                path="/api/v1/quality/deviations",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is True
        assert "quality:read" in data["reason"]
        assert data["required"] is None
        # 质量路径已登记端点内精校验，允许与拒绝判定均附带标注
        assert data["note"] is not None and "精校验" in data["note"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_denied_required(db_session) -> None:
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="POST",
                path="/api/v1/quality/deviations",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is False
        assert data["required"] == "quality:write"
        assert data["note"] is not None and "精校验" in data["note"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_extra_scope_note_warehouse(db_session) -> None:
    """放行路径命中端点内精校验注册表时附带 note 标注。"""
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="GET",
                path="/api/v1/warehouse/material-pages/x",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is True
        assert data["note"] is not None
        assert "warehouse" in data["note"]
        assert "dept_scope_hint" not in data
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_denied_with_extra_scope_note(db_session) -> None:
    """拒绝路径命中精校验注册表时，同样附带 note 标注。"""
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="POST",
                path="/api/v1/warehouse/material-pages/x",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is False
        assert data["required"] == "warehouse:write"
        assert data["note"] is not None
        assert "warehouse" in data["note"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_hr_dept_scope_hint_contains(db_session) -> None:
    """HR 前缀 + department 参数：附加可见部门提示（含）。"""
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session, dept_scope=True)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="GET",
                path="/api/v1/hr/employees",
                department="质量管理部",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is True
        assert data["note"] is not None  # hr 前缀命中精校验标注
        assert "含「质量管理部」" in data["dept_scope_hint"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_hr_dept_scope_hint_excludes(db_session) -> None:
    """未配置 HR 可见部门时（白名单空），提示不含目标部门。"""
    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    user, *_ = await _setup_user(db_session)
    try:
        resp = await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(user.id),
                method="GET",
                path="/api/v1/hr/employees",
                department="研发部",
            ),
            current_user=user,
            db=db_session,
        )
        data = json.loads(resp.body)["data"]
        assert data["allowed"] is True
        assert "不含「研发部」" in data["dept_scope_hint"]
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_permission_simulate_user_not_found(db_session) -> None:
    from fastapi import HTTPException

    from app.platform.identity.rbac_api import simulate_permission
    from app.platform.identity.schemas import PermissionSimulateRequest

    with pytest.raises(HTTPException) as exc_info:
        await simulate_permission(
            body=PermissionSimulateRequest(
                user_id=str(uuid4()),
                method="GET",
                path="/api/v1/quality/deviations",
            ),
            current_user=None,
            db=db_session,
        )
    assert exc_info.value.status_code == 404


# ─── 权限清单导出 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_permissions_csv(db_session) -> None:
    from app.platform.identity.rbac_api import export_permissions

    user, *_ = await _setup_user(db_session)
    try:
        resp = await export_permissions(current_user=user, db=db_session)
        assert resp.headers["content-disposition"].startswith(
            'attachment; filename="permissions.csv"'
        )
        assert "text/csv" in resp.headers["content-type"]
        content = resp.body.decode("utf-8")
        assert content.startswith("\ufeff")
        lines = content.splitlines()
        header = lines[0]
        assert "姓名" in header
        assert "部门" in header
        assert "角色" in header
        assert "菜单页面" in header
        assert "高风险业务动作" in header
        assert "权限点" not in header
        assert "数据范围" in header
        user_line = next(line for line in lines[1:] if "权限验证测试用户" in line)
        assert "无页面授权" in user_line
        assert "pv_manual_role" not in user_line
        assert "pv_dept_role" not in user_line
        assert "quality:read" not in user_line
        assert user.department in user_line
        assert "质量管理部" not in user_line  # 旧权限范围不作为新页面授权导出。
    finally:
        await _cleanup_user(db_session, user.id)


# ─── admin 前缀 403（DEV_BYPASS_AUTH=False 独立 app）──────────────────


@pytest.fixture
def _strict_app(monkeypatch):
    """构造 DEV_BYPASS_AUTH=False 的测试 app + 无操作缓存 + NullPool 会话工厂。"""
    from sqlalchemy import pool
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.core.config import Settings
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

    async def _cache_get(key: str):
        return None

    async def _cache_set(key: str, value: str, ex: int = 3600) -> None:
        return None

    # 中间件在 dispatch 内延迟导入 permission_cache，patch 模块级属性生效
    monkeypatch.setattr(
        "app.platform.identity.permission_cache.get_cached_permissions",
        _cache_get,
    )
    monkeypatch.setattr(
        "app.platform.identity.permission_cache.set_cached_permissions",
        _cache_set,
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

    @test_app.get("/api/v1/identity/admin/permissions/export")
    async def admin_export():
        return {"ok": True}

    return test_app, test_factory


def _make_jwt(open_id: str, user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "open_id": open_id,
        "name": "测试用户",
        "iat": now,
        "exp": now + timedelta(seconds=3600),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")


@pytest.mark.asyncio
async def test_admin_endpoint_403_without_admin_permission(_strict_app) -> None:
    test_app, session_factory = _strict_app
    user_id = uuid4()
    try:
        async with session_factory() as db:
            user = User(
                id=user_id,
                name="无权限用户",
                feishu_open_id=f"pv-open-403-{uuid4().hex[:8]}",
            )
            db.add(user)
            await db.commit()

        token = _make_jwt("any-open-id", str(user_id))
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/identity/admin/permissions/export",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            await db.commit()


@pytest.mark.asyncio
async def test_admin_endpoint_200_with_super_admin(_strict_app) -> None:
    test_app, session_factory = _strict_app
    user_id = uuid4()
    try:
        async with session_factory() as db:
            await seed_permissions(db)
            repo = RbacRepository()
            user = User(
                id=user_id,
                name="超管用户",
                feishu_open_id=f"pv-open-admin-{uuid4().hex[:8]}",
            )
            db.add(user)
            await db.flush()
            super_role = await repo.get_role_by_code(db, SUPER_ADMIN_ROLE_CODE)
            await repo.assign_user_role(db, user_id, super_role.id)
            await db.commit()

        token = _make_jwt("any-open-id-admin", str(user_id))
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/identity/admin/permissions/export",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200, resp.text
    finally:
        async with session_factory() as db:
            await _cleanup_user(db, user_id)
            await db.commit()


# 兜底：确认部门映射角色确实由 resolve_user_roles 解析（来源标注依据）
@pytest.mark.asyncio
async def test_setup_department_role_resolved(db_session) -> None:
    user, role_manual, role_dept, menu_bound, menu_unbound = await _setup_user(
        db_session
    )
    try:
        codes = {r.code for r in await resolve_user_roles(db_session, user.id)}
        assert codes == {"pv_manual_role", "pv_dept_role"}
    finally:
        await _cleanup_user(db_session, user.id)


@pytest.mark.asyncio
async def test_dept_rule_matches_by_department_name_with_dept_ids(db_session) -> None:
    """部门名映射回归：用户已持有 feishu_department_ids（登录补全后）时，
    仅配置部门名的规则仍须命中。

    防止回退到“部门名匹配依赖用户无部门 ID”的实现——该实现会在登录补全
    feishu_department_ids 后永久失效（部门→角色自动匹配不上的根因）。
    """
    from app.platform.identity.rbac import resolve_user_roles

    user, role_manual, role_dept, menu_bound, menu_unbound = await _setup_user(
        db_session
    )
    try:
        assert json.loads(user.feishu_department_ids or "[]"), "前置：用户须已有部门 ID"
        role_name_only = Role(
            name="部门名映射角色", code="pv_name_role", is_system=False
        )
        db_session.add(role_name_only)
        await db_session.flush()
        db_session.add(
            DepartmentRoleRule(
                role_id=role_name_only.id,
                feishu_department_id=None,
                department_name=user.department,
            )
        )
        await db_session.flush()

        codes = {r.code for r in await resolve_user_roles(db_session, user.id)}
        assert "pv_name_role" in codes
    finally:
        await _cleanup_user(db_session, user.id)


# ─── 权限缓存写入时间戳（effective_at 数据源）─────────────────────────


@pytest.mark.asyncio
async def test_permission_cache_with_time(monkeypatch) -> None:
    """set 写入时间戳 → 带时间返回；失效后一并清除。"""
    from app.platform.identity import permission_cache as pc

    stored: dict[str, str] = {}

    async def _fake_cache_get(key: str):
        return stored.get(key)

    async def _fake_cache_set(key: str, value: str, ex: int = 3600) -> None:
        stored[key] = value

    async def _fake_cache_delete(key: str) -> None:
        stored.pop(key, None)

    monkeypatch.setattr(pc, "cache_get", _fake_cache_get)
    monkeypatch.setattr(pc, "cache_set", _fake_cache_set)
    monkeypatch.setattr(pc, "cache_delete", _fake_cache_delete)

    await pc.set_cached_permissions("u-cache-ts", ["hr:read"])
    perms, ts = await pc.get_cached_permissions_with_time("u-cache-ts")
    assert perms == ["hr:read"]
    assert ts is not None
    assert datetime.fromisoformat(ts).tzinfo is not None  # UTC ISO，可解析

    await pc.invalidate_permissions("u-cache-ts")
    perms2, ts2 = await pc.get_cached_permissions_with_time("u-cache-ts")
    assert perms2 is None and ts2 is None
