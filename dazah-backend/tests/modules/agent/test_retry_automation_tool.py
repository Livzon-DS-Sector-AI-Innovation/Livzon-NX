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
async def test_retry_automation_run_creates_a_new_run(monkeypatch: Any) -> None:
    source_run_id = uuid4()
    automation_id = uuid4()
    new_run_id = uuid4()
    user: Any = SimpleNamespace(id=uuid4())
    service: Any = SimpleNamespace(
        get_run=AsyncMock(
            side_effect=[
                {
                    "id": str(source_run_id),
                    "automation_id": str(automation_id),
                    "status": "failed",
                },
                {"id": str(new_run_id), "status": "running"},
            ]
        ),
        _require_owner=AsyncMock(),
    )
    execute_manual: Any = AsyncMock(return_value=SimpleNamespace(id=new_run_id))
    monkeypatch.setattr(agent_tools, "_automation_service", lambda context: service)
    monkeypatch.setattr(
        automation_runner.AgentAutomationRunner,
        "execute_manual",
        execute_manual,
    )

    result = await agent_tools.retry_automation_run(
        SimpleNamespace(db=object(), user=user),
        agent_tools.AutomationRunIdInput(run_id=source_run_id),
    )

    service._require_owner.assert_awaited_once()
    execute_manual.assert_awaited_once_with(
        service._require_owner.await_args.args[0],
        automation_id=automation_id,
    )
    assert result["retried_from_run_id"] == str(source_run_id)
    assert result["run"]["id"] == str(new_run_id)


@pytest.mark.anyio
async def test_retry_automation_run_rejects_non_failed_state(monkeypatch: Any) -> None:
    service: Any = SimpleNamespace(
        get_run=AsyncMock(
            return_value={
                "id": str(uuid4()),
                "automation_id": str(uuid4()),
                "status": "completed",
            }
        )
    )
    monkeypatch.setattr(agent_tools, "_automation_service", lambda context: service)

    with pytest.raises(HTTPException) as exc:
        await agent_tools.retry_automation_run(
            SimpleNamespace(db=object(), user=SimpleNamespace(id=uuid4())),
            agent_tools.AutomationRunIdInput(run_id=uuid4()),
        )

    assert exc.value.status_code == 409
