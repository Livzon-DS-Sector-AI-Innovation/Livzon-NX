"""部门数据范围（data_scope）测试：范围解析、子部门展开、过滤 helper。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.platform.identity.data_scope import (
    DepartmentScope,
    _parse_department_ids,
    _resolve_department_scope,
    department_in_clause,
    filter_rows_by_department,
)
from app.platform.identity.models import (
    DataScopeRule,
    Department,
    Role,
    User,
    UserRole,
)

# ─── 纯函数 ──────────────────────────────────────────────────────────


def test_parse_department_ids() -> None:
    assert _parse_department_ids(None) == []
    assert _parse_department_ids("") == []
    assert _parse_department_ids("not-json") == []
    assert _parse_department_ids(json.dumps(["od-a", "od-b"])) == ["od-a", "od-b"]
    assert _parse_department_ids(json.dumps([{"x": 1}])) == []
    assert _parse_department_ids(json.dumps(["od-a", None])) == ["od-a"]


def test_scope_allows() -> None:
    scope = DepartmentScope(is_all=False, department_names={"质量管理部", "生产管理部"})
    assert scope.allows("质量管理部") is True
    assert scope.allows("生产管理部") is True
    assert scope.allows("人力资源部") is False
    assert scope.allows(None) is False
    assert scope.allows("") is False
    assert DepartmentScope(is_all=True).allows("任意部门") is True
    assert DepartmentScope(is_all=True).allows(None) is True


def test_filter_rows_by_department() -> None:
    rows = [
        {"dept": "质量管理部", "id": 1},
        {"dept": "人力资源部", "id": 2},
        {"dept": None, "id": 3},
    ]
    scope = DepartmentScope(is_all=False, department_names={"质量管理部"})
    filtered = filter_rows_by_department(rows, lambda r: r["dept"], scope)
    assert [r["id"] for r in filtered] == [1]
    # is_all 原样返回
    assert (
        filter_rows_by_department(
            rows, lambda r: r["dept"], DepartmentScope(is_all=True)
        )
        is rows
    )


def test_department_in_clause() -> None:
    from sqlalchemy import Column, String

    column = Column("department", String)
    scope = DepartmentScope(is_all=False, department_names={"质量管理部"})
    clause = department_in_clause(column, scope)
    assert clause is not None
    assert clause.right.value == ["质量管理部"]
    # 仅全部范围可以不加过滤；空集合必须失败关闭。
    assert department_in_clause(column, DepartmentScope(is_all=True)) is None
    empty_scope = DepartmentScope(is_all=False, department_names=set())
    assert str(department_in_clause(column, empty_scope)) == "false"


# ─── 范围解析（真实部门树 + 角色）──────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_scope_subtree_expansion(db_session) -> None:
    """普通用户：本部门 + 全部子孙部门。"""
    # 部门树：生产管理部 → 101一车间 / 102一车间；质量管理部（无子部门）
    db_session.add_all(
        [
            Department(feishu_department_id="od-prod", name="生产管理部"),
            Department(
                feishu_department_id="od-ws101",
                name="101一车间",
                parent_feishu_department_id="od-prod",
            ),
            Department(
                feishu_department_id="od-ws102",
                name="102一车间",
                parent_feishu_department_id="od-prod",
            ),
            Department(feishu_department_id="od-qa", name="质量管理部"),
        ]
    )
    user = User(
        name="车间用户",
        feishu_open_id="test-open-id-scope-1",
        department="101一车间",
        feishu_department_ids=json.dumps(["od-ws101"]),
    )
    db_session.add(user)
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is False
    # 本部门 + 父级无 + 兄弟无（只向下展开，不含父/兄弟）
    assert scope.department_names == {"101一车间"}


@pytest.mark.asyncio
async def test_resolve_scope_from_parent_center(db_session) -> None:
    """用户属于上级部门时，可见全部下级部门。"""
    db_session.add_all(
        [
            Department(feishu_department_id="od-prod", name="生产管理部"),
            Department(
                feishu_department_id="od-ws101",
                name="101一车间",
                parent_feishu_department_id="od-prod",
            ),
            Department(
                feishu_department_id="od-ws102",
                name="102一车间",
                parent_feishu_department_id="od-prod",
            ),
            Department(
                feishu_department_id="od-ws201",
                name="201一车间",
                parent_feishu_department_id="od-ws102",
            ),
        ]
    )
    user = User(
        name="生产管理部用户",
        feishu_open_id="test-open-id-scope-2",
        department="生产管理部",
        feishu_department_ids=json.dumps(["od-prod"]),
    )
    db_session.add(user)
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is False
    assert scope.department_names == {
        "生产管理部",
        "101一车间",
        "102一车间",
        "201一车间",
    }


@pytest.mark.asyncio
async def test_resolve_scope_department_name_fallback(db_session) -> None:
    """无飞书部门 ID 时按 department 部门名兜底（仅自身）。"""
    user = User(
        name="无部门ID用户",
        feishu_open_id="test-open-id-scope-3",
        department="质量管理部",
        feishu_department_ids=None,
    )
    db_session.add(user)
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is False
    assert scope.department_names == {"质量管理部"}


@pytest.mark.asyncio
async def test_resolve_scope_super_admin_all(db_session) -> None:
    """super_admin 角色 → is_all。"""
    await _seed_super_admin(db_session)
    user = User(
        name="超管用户",
        feishu_open_id="test-open-id-scope-4",
        department="质量管理部",
    )
    db_session.add(user)
    await db_session.flush()
    role = (
        await db_session.execute(select(Role).where(Role.code == "super_admin"))
    ).scalar_one()
    db_session.add(UserRole(user_id=user.id, role_id=role.id, source="manual"))
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is True


# ─── 规则配置解析优先级 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_scope_user_rule_overrides_role_rule(db_session) -> None:
    """用户级配置覆盖角色级与默认。"""
    role = Role(name="普通角色", code="scope_role_1", is_system=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        name="高管用户",
        feishu_open_id="test-open-id-scope-5",
        department="103一车间",
        feishu_department_ids=json.dumps(["od-ws103"]),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id, source="manual"))
    # 角色级：指定部门
    db_session.add(
        DataScopeRule(
            role_id=role.id,
            scope_type="departments",
            department_names=json.dumps(["101一车间"], ensure_ascii=False),
        )
    )
    # 用户级：全部（高管覆盖）
    db_session.add(
        DataScopeRule(
            user_id=user.id,
            scope_type="all",
        )
    )
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is True


@pytest.mark.asyncio
async def test_resolve_scope_role_rule_union(db_session) -> None:
    """角色级规则并集；任一 all → 全部。"""
    role_a = Role(name="角色A", code="scope_role_a", is_system=False)
    role_b = Role(name="角色B", code="scope_role_b", is_system=False)
    db_session.add_all([role_a, role_b])
    await db_session.flush()
    user = User(
        name="双角色用户",
        feishu_open_id="test-open-id-scope-6",
        department="101一车间",
        feishu_department_ids=json.dumps(["od-ws101"]),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            UserRole(user_id=user.id, role_id=role_a.id, source="manual"),
            UserRole(user_id=user.id, role_id=role_b.id, source="manual"),
        ]
    )
    # 角色A 指定部门；角色B 全部 → 并集=全部
    db_session.add(
        DataScopeRule(
            role_id=role_a.id,
            scope_type="departments",
            department_names=json.dumps(["101一车间"], ensure_ascii=False),
        )
    )
    db_session.add(DataScopeRule(role_id=role_b.id, scope_type="all"))
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is True


@pytest.mark.asyncio
async def test_resolve_scope_role_rule_departments(db_session) -> None:
    """角色级指定部门列表生效（覆盖默认部门树）。"""
    role = Role(name="跨部门角色", code="scope_role_c", is_system=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        name="跨部门用户",
        feishu_open_id="test-open-id-scope-7",
        department="101一车间",
        feishu_department_ids=json.dumps(["od-ws101"]),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id, source="manual"))
    db_session.add(
        DataScopeRule(
            role_id=role.id,
            scope_type="departments",
            department_names=json.dumps(
                ["质量管理部", "102一车间"], ensure_ascii=False
            ),
        )
    )
    await db_session.flush()

    scope = await _resolve_department_scope(db_session, user)
    assert scope.is_all is False
    assert scope.department_names == {"质量管理部", "102一车间"}


async def _seed_super_admin(db_session) -> None:
    role = (
        await db_session.execute(select(Role).where(Role.code == "super_admin"))
    ).scalar_one_or_none()
    if role is None:
        db_session.add(Role(name="超级管理员", code="super_admin", is_system=True))
        await db_session.flush()
