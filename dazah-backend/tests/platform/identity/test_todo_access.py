from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity import todo_access
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.models import Department, User
from app.platform.identity.todo_access import (
    resolve_todo_actor,
    todo_department_ids,
)
from tests.todo_helpers import make_todo_user


@pytest.mark.asyncio
async def test_legacy_scope_retains_department_policy_and_namesakes_are_not_matched(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_todo_user(db_session)
    db_session.add(User(id=uuid4(), name=user.name, status="active"))
    await db_session.flush()
    request = Request({"type": "http", "headers": []})
    request.state.page_permission = SimpleNamespace(
        permissions=["access", "query", "operate"], sensitive_actions=[]
    )
    tokens = (
        current_page_actor.set(user),
        current_page_key.set("equipment:inspection"),
        current_page_data_scope.set({"scope_type": "not_applicable"}),
    )

    async def resolve(_db: AsyncSession, _user: User) -> DepartmentScope:
        assert current_page_data_scope.get() is None
        return DepartmentScope(department_names={"本部门"})

    monkeypatch.setattr(todo_access, "resolve_user_department_scope", resolve)
    try:
        actor = await resolve_todo_actor(request, db_session, user)
        assert actor.scope.department_names == {"本部门"}
        assert actor.unique_name is None
        assert actor.person_ids == (str(user.id),)
        assert current_page_data_scope.get() == {"scope_type": "not_applicable"}
    finally:
        current_page_actor.reset(tokens[0])
        current_page_key.reset(tokens[1])
        current_page_data_scope.reset(tokens[2])


@pytest.mark.asyncio
async def test_missing_context_rejects_before_scope_or_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), name="测试", role="user")
    request = Request({"type": "http", "headers": []})
    resolver = AsyncMock()
    monkeypatch.setattr(todo_access, "resolve_user_department_scope", resolver)
    token = current_page_actor.set(None)
    try:
        with pytest.raises(HTTPException) as error:
            await resolve_todo_actor(request, AsyncMock(), user)
        assert error.value.status_code == 403
        resolver.assert_not_awaited()
    finally:
        current_page_actor.reset(token)


@pytest.mark.asyncio
async def test_equipment_department_id_mapping_rejects_ambiguous_names(
    db_session: AsyncSession,
) -> None:
    name = f"同名部门{uuid4().hex}"
    db_session.add_all(
        [
            Department(name=name, feishu_department_id=f"d-{uuid4().hex}"),
            Department(name=name, feishu_department_id=f"d-{uuid4().hex}"),
        ]
    )
    await db_session.flush()
    assert (
        await todo_department_ids(db_session, DepartmentScope(department_names={name}))
        == set()
    )
    assert await todo_department_ids(db_session, DepartmentScope(is_all=True)) is None
