import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

from app.platform.identity.models import Role, User, UserRole


@pytest.mark.asyncio
async def test_merge_preserves_ordinary_users_and_only_promotes_manual_admins(
    db_session, monkeypatch
):
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/f7b2d9a4c103_unify_system_administrators.py"
    )
    spec = importlib.util.spec_from_file_location("administrator_merge", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    role = await db_session.scalar(select(Role).where(Role.code == "super_admin"))
    if role is None:
        role = Role(code="super_admin", name="超级管理员", is_system=True)
        db_session.add(role)
    ordinary = User(name="普通用户", role="user", grant_version=7)
    admin = User(name="原管理员", role="admin", grant_version=8)
    legacy = User(name="原超级管理员", role="user", grant_version=9)
    db_session.add_all([ordinary, admin, legacy])
    await db_session.flush()
    db_session.add(UserRole(user_id=legacy.id, role_id=role.id, source="manual"))
    await db_session.flush()
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    for statement in statements:
        await db_session.execute(statement)
    for user in (ordinary, admin, legacy):
        await db_session.refresh(user)
    await db_session.refresh(role)
    assert (ordinary.role, ordinary.grant_version) == ("user", 7)
    assert (admin.role, admin.grant_version) == ("admin", 9)
    assert (legacy.role, legacy.grant_version) == ("admin", 10)
    assert role.name == "系统管理员"
    statements.clear()
    migration.downgrade()
    assert statements == []  # No implicit demotion or reversal of later decisions.
