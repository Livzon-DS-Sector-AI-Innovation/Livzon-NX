"""菜单数据库化测试：种子、仓储 CRUD、权限码校验、按钮级权限解析、菜单 API。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.models import User
from app.platform.identity.rbac import (
    _flatten_seed_menus,
    resolve_user_menu_ids,
    resolve_user_permissions,
    seed_menus,
)
from app.platform.identity.repository import MenuRepository, RbacRepository
from app.platform.identity.schemas import (
    MenuCreateRequest,
    MenuUpdateRequest,
)


@pytest.fixture(autouse=True)
async def _authenticate_menu_api(db_session):
    """Use an explicit admin identity for the current RBAC API contract."""

    user = (
        (
            await db_session.execute(
                select(User)
                .where(User.role == "admin", User.is_deleted.is_(False))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        pytest.skip("当前测试数据库未提供可用于审计的管理员账号")

    async def _current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ─── 种子数据 ────────────────────────────────────────────────────────


def test_seed_keys_globally_unique() -> None:
    """打平后 key 全局唯一（父级拼接），避免数据库中 key 冲突。"""
    flat = _flatten_seed_menus(SEED_MENUS)
    keys = [n["key"] for n in flat]
    assert len(keys) == len(set(keys)), "种子菜单 key 存在重复"
    assert "production" in keys
    assert "safety:risk-hazard:regulation" in keys
    assert "registration:regulation" in keys  # 不同父级下同名义项不冲突


@pytest.mark.asyncio
async def test_seed_menus_structure_and_idempotent(db_session) -> None:
    """seed_menus：目录/菜单类型、父子关系、disabled→status、幂等。"""
    await seed_menus(db_session)
    repo = MenuRepository()
    menus = await repo.list_all(db_session)

    # 共享测试库可能保留其他测试创建的根节点；种子根节点必须全部存在。
    roots = [m for m in menus if m.parent_id is None]
    root_keys = {menu.key for menu in roots}
    assert {node["key"] for node in SEED_MENUS} <= root_keys

    # 目录类型推断：有 children → directory，叶子 → menu
    production = next(m for m in menus if m.key == "production")
    assert production.type == "directory"
    assert production.status == "active"
    batches = next(m for m in menus if m.key == "production:batches")
    assert batches.type == "menu"
    assert batches.parent_id == production.id
    assert batches.route_path == "/production/batches"

    # disabled 种子 → status=disabled
    emergency_plan = next(
        m for m in menus if m.key == "safety:emergency-accident:emergency-plan"
    )
    assert emergency_plan.status == "disabled"

    # permission_code 映射（hr:write）
    dept_mapping = next(
        m for m in menus if m.key == "hr:hr-settings:hr-settings-dept-mapping"
    )
    assert dept_mapping.permission_code == "hr:write"

    # 幂等：再次种子不重复插入
    before = len(menus)
    await seed_menus(db_session)
    after = len(await repo.list_all(db_session))
    assert before == after


# ─── MenuRepository ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_menu_repo_crud(db_session) -> None:
    """菜单 CRUD：创建含父节点、更新、禁删前置查询（子节点）、软删除。"""
    repo = MenuRepository()
    parent = await repo.create(
        db_session, name="测试目录", type="directory", sort_order=99
    )
    child = await repo.create(
        db_session,
        name="测试菜单",
        type="menu",
        parent_id=parent.id,
        route_path="/test/page",
        permission_code="test:page:query",
        sort_order=1,
    )
    assert child.parent_id == parent.id
    assert child.permission_code == "test:page:query"

    # 子节点查询（删除保护）
    children = await repo.list_children(db_session, parent.id)
    assert [c.id for c in children] == [child.id]

    # 更新
    await repo.update(db_session, child, name="测试菜单 v2", sort_order=2)
    assert child.name == "测试菜单 v2"
    assert child.sort_order == 2

    # 软删除：菜单置删除 + role_menus 绑定级联软删
    await repo.soft_delete(db_session, child)
    assert child.is_deleted is True
    # 软删除后查询过滤
    assert (await repo.get_by_id(db_session, child.id)) is None


@pytest.mark.asyncio
async def test_menu_repo_role_menus(db_session) -> None:
    """角色-菜单绑定：设置、查询、全量替换。"""
    repo = MenuRepository()
    rbac = RbacRepository()
    role = await rbac.create_role(
        db_session, name="菜单测试角色", code="menu_test_role"
    )
    m1 = await repo.create(db_session, name="菜单A", type="menu")
    m2 = await repo.create(db_session, name="菜单B", type="menu")

    await repo.set_role_menus(db_session, role.id, [m1.id, m2.id])
    ids = await repo.list_role_menu_ids(db_session, role.id)
    assert set(ids) == {m1.id, m2.id}

    # 全量替换：只留 m1
    await repo.set_role_menus(db_session, role.id, [m1.id])
    ids = await repo.list_role_menu_ids(db_session, role.id)
    assert ids == [m1.id]


# ─── Schema 校验 ─────────────────────────────────────────────────────


def test_menu_create_permission_code_validation() -> None:
    """菜单请求校验当前只约束长度，权限码由权限解析层解释。"""
    item = MenuCreateRequest(
        name="x", type="button", permission_code="hr:employee:create"
    )
    assert item.permission_code == "hr:employee:create"
    with pytest.raises(ValidationError):
        MenuCreateRequest(name="x", type="button", permission_code="x" * 129)


def test_menu_update_cleared_fields() -> None:
    """更新请求保留显式字段，由 API 层用 exclude_unset 应用更新。"""
    req = MenuUpdateRequest(name="改名", permission_code="", route_path=None)
    fields = req.model_dump(exclude_unset=True)
    assert fields["name"] == "改名"
    assert fields["permission_code"] == ""
    assert fields["route_path"] is None  # 显式置空路由
    assert "status" not in fields


# ─── 按钮级权限解析 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_permissions_merges_role_buttons(db_session) -> None:
    """角色勾选按钮菜单 → 按钮码并入用户 permissions。"""
    await seed_menus(db_session)
    rbac = RbacRepository()
    role = await rbac.get_role_by_code(db_session, "btn_role")
    if role is None:
        role = await rbac.create_role(db_session, name="按钮角色", code="btn_role")
    perms = await rbac.list_permissions(db_session)
    quality_read = [p for p in perms if p.code == "quality:read"]
    await rbac.set_role_permissions(db_session, role.id, [p.id for p in quality_read])

    # 创建按钮菜单并绑定角色
    repo = MenuRepository()
    btn = await repo.create(
        db_session,
        name="新建按钮",
        type="button",
        permission_code="quality:deviation:create",
    )
    await repo.set_role_menus(db_session, role.id, [btn.id])

    from uuid import uuid4

    from app.platform.identity.models import User, UserRole

    user_id = uuid4()
    db_session.add(User(id=user_id, name="按钮用户", feishu_open_id="test-open-id-btn"))
    db_session.add(UserRole(user_id=user_id, role_id=role.id, source="manual"))
    await db_session.flush()

    try:
        permissions = await resolve_user_permissions(db_session, user_id)
        code_set = set(permissions)
        # 模块级保持
        assert "quality:read" in code_set
        # 勾选按钮码并入
        assert "quality:deviation:create" in code_set
        # 兼容规则：quality:write 未授予，不自动展开按钮码
        assert "quality:write" not in code_set
    finally:
        from sqlalchemy import delete

        await db_session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await db_session.execute(delete(User).where(User.id == user_id))
        await db_session.flush()


@pytest.mark.asyncio
async def test_resolve_permissions_write_expands_module_buttons(db_session) -> None:
    """兼容规则：持 {module}:write 自动拥有该模块全部按钮码。"""
    await seed_menus(db_session)
    rbac = RbacRepository()
    role = await rbac.get_role_by_code(db_session, "btn_role2")
    if role is None:
        role = await rbac.create_role(db_session, name="按钮角色2", code="btn_role2")
    repo = MenuRepository()
    btn = await repo.create(
        db_session,
        name="设备新增",
        type="button",
        permission_code="equipment:asset:create",
    )
    await repo.set_role_menus(db_session, role.id, [btn.id])

    perms = await rbac.list_permissions(db_session)
    equipment_write = [p for p in perms if p.code == "equipment:write"]
    await rbac.set_role_permissions(
        db_session, role.id, [p.id for p in equipment_write]
    )

    from uuid import uuid4

    from app.platform.identity.models import User, UserRole

    user_id = uuid4()
    db_session.add(User(id=user_id, name="展开用户", feishu_open_id="test-open-id-exp"))
    db_session.add(UserRole(user_id=user_id, role_id=role.id, source="manual"))
    await db_session.flush()

    try:
        permissions = await resolve_user_permissions(db_session, user_id)
        # 模块 write 展开该模块全量按钮码（含本库中所有 equipment: 前缀按钮码）
        expanded = {p for p in permissions if p.startswith("equipment:")}
        assert "equipment:asset:create" in expanded
        # 其他模块按钮码不展开
        assert not any(p.startswith("quality:") for p in permissions)
    finally:
        from sqlalchemy import delete

        await db_session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await db_session.execute(delete(User).where(User.id == user_id))
        await db_session.flush()


@pytest.mark.asyncio
async def test_resolve_user_menu_ids_ancestors(db_session) -> None:
    """用户可见菜单 ids：角色绑定并集 + 祖先补全。"""
    await seed_menus(db_session)
    repo = MenuRepository()
    menus = await repo.list_all(db_session)
    production = next(m for m in menus if m.key == "production")
    batches = next(m for m in menus if m.key == "production:batches")

    rbac = RbacRepository()
    role = await rbac.create_role(db_session, name="菜单树角色", code="menu_tree_role")
    await repo.set_role_menus(db_session, role.id, [batches.id])

    from uuid import uuid4

    from app.platform.identity.models import User, UserRole

    user_id = uuid4()
    db_session.add(User(id=user_id, name="树用户", feishu_open_id="test-open-id-tree"))
    db_session.add(UserRole(user_id=user_id, role_id=role.id, source="manual"))
    await db_session.flush()

    try:
        ids = await resolve_user_menu_ids(db_session, user_id)
        id_set = set(ids)
        # 勾选的叶子 + 祖先（production 目录）均可见
        assert batches.id in id_set
        assert production.id in id_set
    finally:
        from sqlalchemy import delete

        await db_session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        await db_session.execute(delete(User).where(User.id == user_id))
        await db_session.flush()


# ─── 菜单 API（DEV_BYPASS_AUTH 免登录全链路）────────────────────────


@pytest.mark.asyncio
async def test_admin_menu_crud_api(client) -> None:
    """菜单管理 API：新建→查询→更新→删除（软删）→角色绑定。"""
    suffix = uuid4().hex[:8]
    directory_name = f"API目录-{suffix}"
    page_name = f"API页面-{suffix}"
    # 新建
    resp = await client.post(
        "/api/v1/identity/admin/menus",
        json={
            "key": f"api-directory-{suffix}",
            "name": directory_name,
            "type": "directory",
            "sort_order": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()["data"]
    menu_id = created["id"]

    # 子菜单
    resp = await client.post(
        "/api/v1/identity/admin/menus",
        json={
            "key": f"api-page-{suffix}",
            "name": page_name,
            "type": "menu",
            "parent_id": menu_id,
            "route_path": "/api/test-page",
            "permission_code": "test:page:query",
        },
    )
    assert resp.status_code == 200, resp.text
    child_id = resp.json()["data"]["id"]

    # 列表
    resp = await client.get("/api/v1/identity/admin/menus")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["data"]]
    assert menu_id in ids and child_id in ids

    # 有子节点禁删（只能禁用）
    resp = await client.delete(f"/api/v1/identity/admin/menus/{menu_id}")
    assert resp.status_code == 400, resp.text

    # 更新
    resp = await client.put(
        f"/api/v1/identity/admin/menus/{menu_id}",
        json={"name": f"{directory_name}-v2", "status": "disabled"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["name"] == f"{directory_name}-v2"

    # 软删除子节点
    resp = await client.delete(f"/api/v1/identity/admin/menus/{child_id}")
    assert resp.status_code == 200, resp.text
    resp = await client.get("/api/v1/identity/admin/menus")
    assert child_id not in [m["id"] for m in resp.json()["data"]]

    # 超长权限码由 Pydantic 校验拒绝
    resp = await client.post(
        "/api/v1/identity/admin/menus",
        json={"name": "非法", "type": "button", "permission_code": "x" * 129},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_role_menus_api_and_user_menus(client, db_session) -> None:
    """角色菜单绑定 API + 用户菜单端点。"""
    await seed_menus(db_session)
    await db_session.commit()

    role_code = f"api_menu_role_{uuid4().hex[:8]}"
    # 角色
    resp = await client.post(
        "/api/v1/identity/admin/roles",
        json={"name": "API菜单角色", "code": role_code},
    )
    assert resp.status_code == 200, resp.text
    role_id = resp.json()["data"]["id"]

    # 查询菜单（种子数据）
    resp = await client.get("/api/v1/identity/admin/menus")
    menus = resp.json()["data"]
    production = next(m for m in menus if m.get("key") == "production")
    batches = next(m for m in menus if m.get("key") == "production:batches")

    # 设置角色菜单
    resp = await client.put(
        f"/api/v1/identity/admin/roles/{role_id}/menus",
        json={"menu_ids": [production["id"], batches["id"]]},
    )
    assert resp.status_code == 200, resp.text

    # 查询角色菜单
    resp = await client.get(f"/api/v1/identity/admin/roles/{role_id}/menus")
    assert resp.status_code == 200
    assert set(resp.json()["data"]["menu_ids"]) == {
        production["id"],
        batches["id"],
    }

    # 系统角色禁改菜单
    resp = await client.get("/api/v1/identity/admin/roles")
    super_role = next(r for r in resp.json()["data"] if r["code"] == "super_admin")
    resp = await client.put(
        f"/api/v1/identity/admin/roles/{super_role['id']}/menus",
        json={"menu_ids": []},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_menu_seed_rows_exist_for_user_endpoint(client, db_session) -> None:
    """用户菜单端点基于种子数据返回：顶层目录与嵌套子菜单结构完整。"""
    pytest.skip("当前平台未保留迁移前 /identity/menus/user 包装接口")
    await seed_menus(db_session)

    resp = await client.get("/api/v1/identity/menus/user")
    data = resp.json()["data"]
    keys = {m.get("key") for m in data}
    # 种子 key（含拼接层级）应出现在用户菜单中
    assert "production" in keys
    assert "production:batches" in keys
    assert "quality:inspection:inspection-finished" in keys
    # 禁用项（开发中）不返回（按名称判断，种子 name 含"（开发中）"）
    assert not any("（开发中）" in (m["name"] or "") for m in data)
