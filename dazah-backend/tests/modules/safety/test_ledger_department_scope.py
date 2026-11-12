from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ForbiddenException
from app.modules.safety import page_scope
from app.modules.safety.api import hazards
from app.modules.safety.feishu import IdentityResolver
from app.modules.safety.repository import SafetyRepository
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)


@pytest.mark.parametrize(
    ("page", "resource", "table"),
    [
        ("training-check:safety-check", "check", "safety_checks"),
        ("emergency-accident:accident-ledger", "accident", "accidents"),
        (
            "risk-hazard:hazard-inspection:hazard-inspection-ledger",
            "hazard",
            "hazard_reports",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ledger_scope_applies_to_reads_and_writes(
    monkeypatch, page, resource, table
):
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
        scalar_one_or_none=lambda: None,
        rowcount=0,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=result), scalar=AsyncMock(return_value=0)
    )
    db.add = Mock()
    resolve_scope = AsyncMock(return_value=DepartmentScope(department_names={"质量部"}))
    monkeypatch.setattr(page_scope, "resolve_user_department_scope", resolve_scope)
    key = current_page_key.set(f"safety:{page}")
    actor = current_page_actor.set(SimpleNamespace(role="user"))
    scope = current_page_data_scope.set({"scope_type": "department_tree"})
    repo = SafetyRepository(db)
    record_id = uuid4()
    try:
        assert await getattr(repo, f"get_{resource}s")() == ([], 0)
        assert await getattr(repo, f"get_{resource}_by_id")(record_id) is None
        assert await getattr(repo, f"update_{resource}")(record_id, {}) is None
        assert not await getattr(repo, f"delete_{resource}")(record_id)
        for call in [*db.scalar.await_args_list, *db.execute.await_args_list]:
            statement = call.args[0].compile(dialect=postgresql.dialect())
            assert f"{table}.department IN" in str(statement)
            assert ["质量部"] in statement.params.values()
        db.execute.reset_mock()
        with pytest.raises(ForbiddenException):
            await getattr(repo, f"create_{resource}")({"department": "外部部门"})
        with pytest.raises(ForbiddenException):
            await getattr(repo, f"update_{resource}")(
                record_id, {"department": "外部部门"}
            )
        db.add.assert_not_called()
        db.execute.assert_not_awaited()
    finally:
        current_page_data_scope.reset(scope)
        current_page_actor.reset(actor)
        current_page_key.reset(key)


@pytest.mark.parametrize("resolved_department", ["质量部", "外部部门", None])
@pytest.mark.asyncio
async def test_department_leader_requires_scope_on_resolved_department(
    monkeypatch, resolved_department
):
    monkeypatch.setattr(
        hazards,
        "ledger_department_scope",
        AsyncMock(return_value=DepartmentScope(department_names={"质量部"})),
    )
    resolver = AsyncMock(
        return_value=SimpleNamespace(
            name="测试负责人", department=resolved_department, id=None
        )
    )
    monkeypatch.setattr(IdentityResolver, "resolve_department_leader", resolver)
    if resolved_department == "质量部":
        response = await hazards.get_department_leader("质量部", db=SimpleNamespace())
        assert response.data.department == "质量部"
    else:
        with pytest.raises(ForbiddenException):
            await hazards.get_department_leader("质量部", db=SimpleNamespace())
    resolver.assert_awaited_once_with("质量部")
