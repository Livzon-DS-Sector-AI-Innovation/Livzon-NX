import uuid

import pytest

from app.modules.agent.repository import AgentRepository
from app.platform.identity.repository import FeishuCardActionRepository


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


@pytest.mark.anyio
async def test_feishu_card_action_query_uses_row_lock() -> None:
    db = CapturingDb()

    await FeishuCardActionRepository().get_by_id_for_update(db, uuid.uuid4())

    assert db.statements[0]._for_update_arg is not None
