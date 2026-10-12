from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.agent import agent_tools, automation_runner
from app.modules.agent.repository import AgentRepository

SimpleNamespace: Any = _SimpleNamespace


class _RepositoryDb:
    def __init__(self: Any) -> None:
        self.added = None

    def add(self: Any, value: Any) -> None:
        self.added = value

    async def flush(self: Any) -> None:
        return None


@pytest.mark.anyio
async def test_tool_call_uses_top_level_trace_id_as_correlation() -> None:
    trace_id = uuid4()
    db = _RepositoryDb()

    call = await AgentRepository().create_tool_call(
        db,  # type: ignore[arg-type]
        session_id=None,
        operation="agent.get_current_time",
        request_payload={"trace_id": str(trace_id)},
    )

    assert call.correlation_id == trace_id


@pytest.mark.anyio
async def test_retry_tool_delegates_to_owner_checked_resume(monkeypatch: Any) -> None:
    run_id = uuid4()
    user: Any = SimpleNamespace(id=uuid4())
    service: Any = SimpleNamespace(
        get_run=AsyncMock(
            return_value={
                "run": {"id": str(run_id), "status": "succeeded"},
                "steps": [],
            }
        )
    )
    resume: Any = AsyncMock(return_value=SimpleNamespace(id=run_id))
    monkeypatch.setattr(agent_tools, "_automation_service", lambda context: service)
    monkeypatch.setattr(automation_runner.AgentAutomationRunner, "retry_failed", resume)
    db = object()
    result = await agent_tools.retry_automation_run(
        SimpleNamespace(db=db, user=user),
        agent_tools.AutomationRunIdInput(run_id=run_id),
    )
    resume.assert_awaited_once_with(db, run_id=run_id, user=user)
    assert result["run"]["run"]["id"] == str(run_id)
    assert result["retried_from_run_id"] == str(run_id)


@pytest.mark.anyio
async def test_retry_tool_preserves_resume_rejection(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        agent_tools, "_automation_service", lambda context: SimpleNamespace()
    )
    monkeypatch.setattr(
        automation_runner.AgentAutomationRunner,
        "retry_failed",
        AsyncMock(side_effect=HTTPException(409, "非幂等写入")),
    )
    with pytest.raises(HTTPException) as exc:
        await agent_tools.retry_automation_run(
            SimpleNamespace(db=object(), user=SimpleNamespace(id=uuid4())),
            agent_tools.AutomationRunIdInput(run_id=uuid4()),
        )
    assert exc.value.status_code == 409
