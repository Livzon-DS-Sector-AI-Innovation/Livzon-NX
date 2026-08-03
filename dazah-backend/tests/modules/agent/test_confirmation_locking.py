import uuid

import pytest

from app.modules.agent.repository import AgentRepository


class EmptyResult:
    def scalar_one_or_none(self):
        return None


class CapturingDb:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return EmptyResult()


@pytest.mark.anyio
async def test_confirmation_execution_query_uses_row_lock() -> None:
    db = CapturingDb()

    await AgentRepository().get_confirmation_for_update(db, uuid.uuid4())

    assert db.statements[0]._for_update_arg is not None
