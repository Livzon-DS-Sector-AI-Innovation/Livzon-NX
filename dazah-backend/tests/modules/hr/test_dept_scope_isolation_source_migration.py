"""人事/培训模块部门级数据隔离测试。

覆盖：
- resolve_visible_dept_alias_set 三分支（管理员 hr:write/配置表/自动自己部门）
- _assert_dept_in_scope 越权 403
- 员工列表接口按可见范围过滤 + 越权部门 403
- 培训部门列表接口过滤
- dept-scopes 管理 API（PUT/GET/DELETE）

说明：DEV_BYPASS_AUTH=true 时权限中间件放行，dev 用户无任何角色，
接口内 resolve_user_permissions 由 monkeypatch 控制（非管理员/管理员场景）。
"""

from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.hr.training_dept_resolver as _resolver_mod
from app.core.database import get_db
from app.core.exceptions import AppException
from app.main import app
from app.modules.hr.api import _assert_dept_in_scope
from app.modules.hr.models import Employee, HrUserDeptScope, TrainingLedger
from app.modules.hr.training_dept_resolver import resolve_visible_dept_alias_set
from app.platform.identity.models import User

# 独有虚拟部门，真实数据不会命中
DEPT_A = "SPEC隔离车间A"
DEPT_B = "SPEC隔离车间B"
# dev 绕过模式下固定用户 ID（app.core.deps.get_current_user 创建）
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
DEV_OPEN_ID = "hr-source-migration-open-id"


@pytest.fixture(autouse=True)
async def _share_db_session(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[None]:
    """Make API calls observe rows seeded through the test session."""

    if await db_session.get(User, UUID(DEV_USER_ID)) is None:
        db_session.add(
            User(
                id=UUID(DEV_USER_ID),
                name="范围测试用户",
                username="hr-scope-migration-user",
                role="admin",
                status="active",
                auth_source="local",
                feishu_open_id=DEV_OPEN_ID,
                department=DEPT_A,
            )
        )
        await db_session.flush()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def _patch_mappings(monkeypatch, extra: list[tuple] | None = None):
    """monkeypatch _load_mappings 返回测试用映射数据（替代 mock db 无法查询真实表）。"""
    mappings = [
        {
            "source_name": "103一车间",
            "target_name": "103车间",
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "103二车间",
            "target_name": "103车间",
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "103车间公用部门",
            "target_name": "103车间",
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": "质量管理部",
            "target_name": "QA",
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": DEPT_A,
            "target_name": DEPT_A,
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
        {
            "source_name": DEPT_B,
            "target_name": DEPT_B,
            "match_level": "first",
            "mapping_type": "alias",
            "priority": 100,
        },
    ]
    if extra:
        for s, t, lv, mt, p in extra:
            mappings.append(
                {
                    "source_name": s,
                    "target_name": t,
                    "match_level": lv,
                    "mapping_type": mt,
                    "priority": p,
                }
            )

    async def fake_load(_session):
        return mappings

    monkeypatch.setattr(_resolver_mod, "_load_mappings", fake_load)
    # 清空全局缓存，避免测试间干扰
    _resolver_mod.invalidate_training_dept_mapping_cache()


class _FakeUser:
    def __init__(self, user_id: str, department: str | None = None):
        self.id = user_id
        self.department = department


def _mock_db(scope_obj: MagicMock | None = None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scope_obj
    db.execute.return_value = result
    return db


def _scope_obj(visible_depts: list[str]) -> MagicMock:
    s = MagicMock()
    s.visible_depts = visible_depts
    return s


def _patch_rbac(monkeypatch, perms: list[str]) -> None:
    async def fake_rp(db, user_id):
        return list(perms)

    monkeypatch.setattr("app.platform.identity.rbac.resolve_user_permissions", fake_rp)


# ─── 可见范围解析三分支（单元测试，mock session）───


@pytest.mark.asyncio
async def test_admin_hr_write_sees_all(monkeypatch):
    """有 hr:write 权限 → None（全部可见）"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])
    db = _mock_db()
    user = _FakeUser("u1", department="103一车间")
    assert await resolve_visible_dept_alias_set(db, user) is None


@pytest.mark.asyncio
async def test_admin_super_star_sees_all(monkeypatch):
    """super_admin 通配权限 → None（全部可见）"""
    _patch_rbac(monkeypatch, ["*"])
    db = _mock_db()
    user = _FakeUser("u1")
    assert await resolve_visible_dept_alias_set(db, user) is None


@pytest.mark.asyncio
async def test_configured_scope_expands_aliases(monkeypatch):
    """配置表指定可见部门 → 展开全部档案别名"""
    _patch_rbac(monkeypatch, ["hr:read"])
    _patch_mappings(monkeypatch)
    db = _mock_db(_scope_obj(["103车间", "QA"]))
    user = _FakeUser("u1", department="质量管理部")
    alias_set = await resolve_visible_dept_alias_set(db, user)
    assert alias_set is not None
    # 103车间 自身 + 档案别名（103一车间/103二车间/103车间公用部门）
    assert "103车间" in alias_set
    assert "103一车间" in alias_set
    assert "103二车间" in alias_set
    # QA 自身 + 档案别名（质量管理部）
    assert "QA" in alias_set
    assert "质量管理部" in alias_set


@pytest.mark.asyncio
async def test_no_config_whitelist_sees_nothing(monkeypatch):
    """白名单制：无配置（即使有部门）→ 空集合，什么都看不到"""
    _patch_rbac(monkeypatch, ["hr:read"])
    _patch_mappings(monkeypatch)
    db = _mock_db(None)  # 无配置记录
    user = _FakeUser("u1", department="103一车间")
    alias_set = await resolve_visible_dept_alias_set(db, user)
    assert alias_set is not None
    assert alias_set == set()  # 未配置 = 不可见任何部门


@pytest.mark.asyncio
async def test_no_dept_no_config_sees_nothing(monkeypatch):
    """用户无部门且无配置 → 空集合（安全默认：什么都看不到）"""
    _patch_rbac(monkeypatch, ["hr:read"])
    db = _mock_db(None)
    user = _FakeUser("u1", department=None)
    assert await resolve_visible_dept_alias_set(db, user) == set()


# ─── 越权校验（_assert_dept_in_scope）───


@pytest.mark.asyncio
async def test_assert_dept_in_scope_403(monkeypatch):
    """请求可见范围之外的部门 → 403"""
    _patch_rbac(monkeypatch, ["hr:read"])
    _patch_mappings(monkeypatch)
    db = _mock_db(None)
    user = _FakeUser("u1", department="103一车间")
    with pytest.raises(AppException) as exc_info:
        await _assert_dept_in_scope(db, user, "QA")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_dept_in_scope_pass(monkeypatch):
    """请求可见范围内的部门（含档案别名）→ 通过并返回可见范围"""
    _patch_rbac(monkeypatch, ["hr:read"])
    _patch_mappings(monkeypatch)
    db = _mock_db(_scope_obj(["103车间"]))
    user = _FakeUser("u1", department="103一车间")
    alias_set = await _assert_dept_in_scope(db, user, "103一车间")
    assert alias_set is not None
    assert "103车间" in alias_set


# ─── 接口级测试（client + db_session，全回滚）───


async def _seed_employees(session: AsyncSession) -> None:
    session.add_all(
        [
            Employee(
                employee_number="SPEC-SCOPE-A",
                name="测隔离甲",
                department=DEPT_A,
                position="测试员",
                hire_date=date(2020, 1, 1),
                status="在职",
            ),
            Employee(
                employee_number="SPEC-SCOPE-B",
                name="测隔离乙",
                department=DEPT_B,
                position="测试员",
                hire_date=date(2020, 1, 1),
                status="在职",
            ),
        ]
    )
    await session.flush()


async def _seed_scope(
    session: AsyncSession, user_id: str, visible_depts: list[str]
) -> None:
    """种子可见部门配置并复用已有同 user_id 记录。"""
    from sqlalchemy import select

    parsed_user_id = UUID(user_id)
    if await session.get(User, parsed_user_id) is None:
        session.add(
            User(
                id=parsed_user_id,
                name="范围测试用户",
                username="hr-scope-migration-user",
                role="admin",
                status="active",
                auth_source="local",
                feishu_open_id=DEV_OPEN_ID,
                department=DEPT_A,
            )
        )
        await session.flush()

    result = await session.execute(
        select(HrUserDeptScope).where(HrUserDeptScope.user_id == user_id)
    )
    scope = result.scalar_one_or_none()
    if scope is None:
        session.add(HrUserDeptScope(user_id=user_id, visible_depts=visible_depts))
    else:
        scope.visible_depts = visible_depts
        scope.is_deleted = False
    await session.flush()


@pytest.mark.asyncio
async def test_employee_list_filtered_by_scope(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """非管理员：员工列表只见可见部门人员；越权部门参数 → 403"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:employee:read"])
    await _seed_employees(db_session)
    await _seed_scope(db_session, DEV_USER_ID, [DEPT_A])

    resp = await client.get("/api/v1/hr/employees", params={"page_size": 100})
    assert resp.status_code == 200, resp.text
    names = {e["name"] for e in resp.json()["data"]}
    assert "测隔离甲" in names
    assert "测隔离乙" not in names

    resp403 = await client.get("/api/v1/hr/employees", params={"department": DEPT_B})
    assert resp403.status_code == 403


@pytest.mark.asyncio
async def test_employee_list_admin_sees_all(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """管理员（hr:write）：即使有配置也全部可见"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])
    await _seed_employees(db_session)
    await _seed_scope(db_session, DEV_USER_ID, [DEPT_A])

    resp = await client.get("/api/v1/hr/employees", params={"page_size": 100})
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()["data"]}
    assert "测隔离甲" in names
    assert "测隔离乙" in names


@pytest.mark.asyncio
async def test_training_departments_filtered(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """培训部门列表（部门 Tab 数据源）按可见范围过滤"""
    _patch_rbac(monkeypatch, ["hr:read"])
    db_session.add_all(
        [
            TrainingLedger(
                employee_number="SPEC-SCOPE-TRAIN-A",
                training_date=date(2031, 1, 1),
                training_subject="SPEC隔离台账A",
                teaching_dept=DEPT_A,
                ledger_department=DEPT_A,
                source_type="manual",
            ),
            TrainingLedger(
                employee_number="SPEC-SCOPE-TRAIN-B",
                training_date=date(2031, 1, 2),
                training_subject="SPEC隔离台账B",
                teaching_dept=DEPT_B,
                ledger_department=DEPT_B,
                source_type="manual",
            ),
        ]
    )
    await _seed_scope(db_session, DEV_USER_ID, [DEPT_A])

    resp = await client.get("/api/v1/hr/training/departments")
    assert resp.status_code == 200
    depts = resp.json()["data"]
    assert DEPT_A in depts
    assert DEPT_B not in depts


@pytest.mark.asyncio
async def test_training_ledger_403_on_out_of_scope_dept(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """非管理员按越权部门查台账 → 403"""
    _patch_rbac(monkeypatch, ["hr:read"])
    await _seed_scope(db_session, DEV_USER_ID, [DEPT_A])

    resp = await client.get(
        "/api/v1/hr/training-ledgers", params={"department": DEPT_B}
    )
    assert resp.status_code == 403


# ─── dept-scopes 管理 API（管理员）───


@pytest.mark.asyncio
async def test_dept_scope_crud(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """管理员维护可见部门配置：PUT 保存 → GET 列表可见 → DELETE 清除"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])

    # PUT 保存
    resp = await client.put(
        f"/api/v1/hr/dept-scopes/{DEV_USER_ID}",
        json={"visible_depts": [DEPT_A, DEPT_B]},
    )
    assert resp.status_code == 200
    assert set(resp.json()["data"]["visible_depts"]) == {DEPT_A, DEPT_B}

    # GET 列表（含用户名）
    resp_list = await client.get("/api/v1/hr/dept-scopes")
    assert resp_list.status_code == 200
    items = resp_list.json()["data"]
    match = [i for i in items if i["user_id"] == DEV_USER_ID]
    assert len(match) == 1
    assert set(match[0]["visible_depts"]) == {DEPT_A, DEPT_B}

    # DELETE 清除（回退自动规则）
    resp_del = await client.delete(f"/api/v1/hr/dept-scopes/{DEV_USER_ID}")
    assert resp_del.status_code == 200

    resp_list2 = await client.get("/api/v1/hr/dept-scopes")
    assert all(i["user_id"] != DEV_USER_ID for i in resp_list2.json()["data"])


@pytest.mark.asyncio
async def test_dept_scope_clear_then_resave(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """清除后再次保存应复用软删记录，避免唯一约束冲突。"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])

    # 保存
    resp = await client.put(
        f"/api/v1/hr/dept-scopes/{DEV_USER_ID}",
        json={"visible_depts": [DEPT_A]},
    )
    assert resp.status_code == 200

    # 清除（软删除）
    resp_del = await client.delete(f"/api/v1/hr/dept-scopes/{DEV_USER_ID}")
    assert resp_del.status_code == 200

    # 再保存（之前此处触发 UniqueViolationError → 500）
    resp2 = await client.put(
        f"/api/v1/hr/dept-scopes/{DEV_USER_ID}",
        json={"visible_depts": [DEPT_A, DEPT_B]},
    )
    assert resp2.status_code == 200
    assert set(resp2.json()["data"]["visible_depts"]) == {DEPT_A, DEPT_B}

    # 列表可见且只一条记录
    resp_list = await client.get("/api/v1/hr/dept-scopes")
    matches = [i for i in resp_list.json()["data"] if i["user_id"] == DEV_USER_ID]
    assert len(matches) == 1
    assert set(matches[0]["visible_depts"]) == {DEPT_A, DEPT_B}


@pytest.mark.asyncio
async def test_dept_scope_by_feishu_open_id(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """user_id 参数支持飞书 open_id：解析为系统用户 UUID 后保存（回归用例）"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])
    # dev 用户的 feishu_open_id
    open_id = DEV_OPEN_ID

    resp = await client.put(
        f"/api/v1/hr/dept-scopes/{open_id}",
        json={"visible_depts": [DEPT_A]},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user_id"] == DEV_USER_ID

    # open_id 查询
    resp_get = await client.get(f"/api/v1/hr/dept-scopes/{open_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["data"]["user_id"] == DEV_USER_ID


@pytest.mark.asyncio
async def test_dept_scope_precreate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """提前配置：用户未登录过系统（open_id 无对应用户）也可保存，自动预创建用户记录"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:write"])
    new_open_id = "ou_spec_precreate_user_001"

    resp = await client.put(
        f"/api/v1/hr/dept-scopes/{new_open_id}",
        json={
            "visible_depts": [DEPT_A, DEPT_B],
            "user_name": "测预创建",
            "user_department": "SPEC预创建部",
        },
    )
    assert resp.status_code == 200

    # 预创建的用户记录存在（feishu_open_id 匹配）
    from app.platform.identity.models import User

    result = await db_session.execute(
        select(User).where(User.feishu_open_id == new_open_id)
    )
    pre_user = result.scalar_one_or_none()
    assert pre_user is not None
    assert pre_user.name == "测预创建"
    assert pre_user.department == "SPEC预创建部"

    # 配置已保存且绑定预创建用户的 UUID
    saved_uuid = resp.json()["data"]["user_id"]
    assert saved_uuid == str(pre_user.id)
    resp_list = await client.get("/api/v1/hr/dept-scopes")
    matches = [i for i in resp_list.json()["data"] if i["user_id"] == saved_uuid]
    assert len(matches) == 1
    assert set(matches[0]["visible_depts"]) == {DEPT_A, DEPT_B}


@pytest.mark.asyncio
async def test_whitelist_no_config_sees_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """白名单制：非管理员无配置时员工列表为空（回归用例）"""
    _patch_rbac(monkeypatch, ["hr:read", "hr:employee:read"])
    await _seed_employees(db_session)
    await db_session.execute(
        HrUserDeptScope.__table__.update()
        .where(HrUserDeptScope.user_id == UUID(DEV_USER_ID))
        .values(is_deleted=True)
    )
    await db_session.flush()
    # 不配置任何可见部门

    resp = await client.get("/api/v1/hr/employees", params={"page_size": 100})
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()["data"]}
    assert "测隔离甲" not in names
    assert "测隔离乙" not in names
