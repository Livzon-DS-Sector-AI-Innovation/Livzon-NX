import uuid
from typing import Any

import pytest

from app.modules.agent.repository import AgentRepository


class EmptyResult:
    def scalar_one_or_none(self: Any) -> Any:
        return None


class CapturingDb:
    def __init__(self: Any) -> None:
        self.statements = []  # type: ignore[var-annotated]

    async def execute(self: Any, statement: Any) -> Any:
        self.statements.append(statement)
        return EmptyResult()


@pytest.mark.anyio
async def test_confirmation_execution_query_uses_row_lock() -> None:
    db: Any = CapturingDb()

    await AgentRepository().get_confirmation_for_update(db, uuid.uuid4())

    assert db.statements[0]._for_update_arg is not None
