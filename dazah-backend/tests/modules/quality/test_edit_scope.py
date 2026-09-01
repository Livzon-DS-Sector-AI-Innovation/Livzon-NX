"""质量 QA 细分编辑/所有权校验与角色种子测试。

覆盖 assert_quality_edit_scope / resolve_quality_list_scope 与 QUALITY_QA_ROLE_SEEDS。
"""

from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import AppException
from app.modules.quality.api import deps as quality_deps
from app.modules.quality.models import CapaPlanTrack, ChangeActionPlan, Deviation
from app.platform.identity.data_scope import DepartmentScope


class _User:
    def __init__(self, uid: uuid.UUID, name: str = "测试用户"):
        self.id = uid
        self.name = name


def _patch_permissions(monkeypatch, permissions: list[str]) -> None:
    async def _fake_resolve(db, user_id):
        return list(permissions)

    monkeypatch.setattr(quality_deps, "resolve_user_permissions", _fake_resolve)


async def _assert(
    monkeypatch,
    permissions: list[str],
    *,
    scope_permission: str | None = None,
    record=None,
    user: _User | None = None,
) -> None:
    _patch_permissions(monkeypatch, permissions)
    current = user or _User(uuid.uuid4())
    await quality_deps.assert_quality_edit_scope(
        None,
        current,
        scope_permission=scope_permission,
        record=record,
    )


# ─── assert_quality_edit_scope ───────────────────────────────────────


@pytest.mark.asyncio
async def test_assert_allows_wildcard(monkeypatch) -> None:
    """通配（super_admin / DEV）→ 通过。"""
    await _assert(monkeypatch, ["*"])


@pytest.mark.asyncio
async def test_assert_allows_module_write(monkeypatch) -> None:
    """模块级 quality:write → 通过（跨全部子域）。"""
    await _assert(monkeypatch, ["quality:read", "quality:write"])


@pytest.mark.asyncio
async def test_assert_allows_scope_code(monkeypatch) -> None:
    """命中子域全编辑权限码 → 通过。"""
    await _assert(
        monkeypatch,
        ["quality:read", "quality:system_qa:write"],
        scope_permission=quality_deps.QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )


@pytest.mark.asyncio
async def test_assert_allows_own_created_by(monkeypatch) -> None:
    """记录 created_by == 当前用户 → 通过（仅可编辑自己新建）。"""
    user = _User(uuid.uuid4())
    record = Deviation(created_by=user.id)
    await _assert(monkeypatch, ["quality:read"], record=record, user=user)


@pytest.mark.asyncio
async def test_assert_allows_person_field_name_match(monkeypatch) -> None:
    """记录人员列（负责人/发现人）命中当前用户姓名 → 通过。"""
    user = _User(uuid.uuid4(), name="质量部张三")
    record = Deviation(discoverer="质量部张三")
    await _assert(monkeypatch, ["quality:read"], record=record, user=user)


@pytest.mark.asyncio
async def test_assert_forbidden_other_domain_and_other_owner(monkeypatch) -> None:
    """无子域权限且记录非本人 → 403。"""
    user = _User(uuid.uuid4())
    other = _User(uuid.uuid4())
    record = Deviation(created_by=other.id, discoverer="别人")
    with pytest.raises(AppException) as exc:
        await _assert(
            monkeypatch,
            ["quality:read"],
            scope_permission=quality_deps.QUALITY_QA_SCOPE_PERMISSIONS["qc"],
            record=record,
            user=user,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_forbidden_read_only(monkeypatch) -> None:
    """仅 quality:read 且无记录（飞书门禁场景）→ 403。"""
    with pytest.raises(AppException) as exc:
        await _assert(
            monkeypatch,
            ["quality:read"],
            scope_permission=quality_deps.QUALITY_QA_SCOPE_PERMISSIONS["material_qa"],
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_person_field_registry(monkeypatch) -> None:
    """人员列映射覆盖主要模型。"""
    assert quality_deps._record_person_field_names(Deviation()) == (
        "reporter_id",
        "discoverer",
    )
    assert quality_deps._record_person_field_names(ChangeActionPlan()) == (
        "owner_user_id",
        "owner_name",
    )
    assert quality_deps._record_person_field_names(CapaPlanTrack()) == ("owner_name",)


# ─── resolve_quality_list_scope ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_scope_qa_role_sees_all(monkeypatch) -> None:
    """QA 角色（持质量子域写码）→ 质量模块内全部可见。"""
    _patch_permissions(monkeypatch, ["quality:read", "quality:qc:write"])
    scope = await quality_deps.resolve_quality_list_scope(None, _User(uuid.uuid4()))
    assert scope.is_all is True


@pytest.mark.asyncio
async def test_list_scope_module_write_sees_all(monkeypatch) -> None:
    """quality:write → 全部可见。"""
    _patch_permissions(monkeypatch, ["quality:write"])
    scope = await quality_deps.resolve_quality_list_scope(None, _User(uuid.uuid4()))
    assert scope.is_all is True


@pytest.mark.asyncio
async def test_list_scope_plain_read_uses_department_scope(monkeypatch) -> None:
    """普通 quality:read 角色 → 回退平台默认部门范围。"""

    async def _fake_dept_scope(db, user):
        return DepartmentScope(is_all=False, department_names={"质量部"})

    _patch_permissions(monkeypatch, ["quality:read"])
    monkeypatch.setattr(quality_deps, "resolve_user_department_scope", _fake_dept_scope)
    scope = await quality_deps.resolve_quality_list_scope(None, _User(uuid.uuid4()))
    assert scope.is_all is False
    assert scope.department_names == {"质量部"}


# ─── 角色种子 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_quality_qa_roles(db_session) -> None:
    """seed_permissions 创建 6 个系统 QA 角色并预绑 quality:read + 子域权限。"""
    from app.platform.identity.rbac import QUALITY_QA_ROLE_SEEDS, seed_permissions
    from app.platform.identity.repository import RbacRepository

    await seed_permissions(db_session)
    repo = RbacRepository()
    assert len(QUALITY_QA_ROLE_SEEDS) == 6
    for seed in QUALITY_QA_ROLE_SEEDS:
        role = await repo.get_role_by_code(db_session, seed["code"])
        assert role is not None, f"{seed['code']} 未创建"
        assert role.is_system is True, f"{seed['code']} 应为系统角色"
        perm_codes = await repo.list_role_permission_codes(db_session, role.id)
        for perm_code in seed["permissions"]:
            assert perm_code in perm_codes, f"{seed['code']} 缺少权限 {perm_code}"
