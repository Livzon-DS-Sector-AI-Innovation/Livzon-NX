import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.modules.agent.schemas import AgentToolExecuteRequest
from app.modules.agent.tools import ToolExecutor, ToolRegistry, agent_tool


class EchoInput(BaseModel):
    value: str


class FakeDb:
    def __init__(self, user=None) -> None:
        self.user = user
        self.added = []

    async def get(self, model, item_id):
        if self.user and self.user.id == item_id:
            return self.user
        return None

    def add(self, item) -> None:
        self.added.append(item)


class FakeRepo:
    def __init__(self) -> None:
        self.tool_calls = []
        self.confirmations = []

    async def get_session(self, db, session_id):
        return None

    async def create_tool_call(self, db, *, session_id, operation, request_payload):
        call = SimpleNamespace(
            session_id=session_id,
            operation=operation,
            request_payload=request_payload,
            status="started",
            response_payload=None,
            error_message=None,
        )
        self.tool_calls.append(call)
        return call

    async def finish_tool_call(
        self,
        db,
        call,
        *,
        status,
        response_payload=None,
        error_message=None,
    ):
        call.status = status
        call.response_payload = response_payload
        call.error_message = error_message
        return call

    async def create_confirmation(
        self,
        db,
        *,
        session_id,
        user_id,
        operation,
        summary,
        risk_level,
        request_payload,
        expires_at,
    ):
        confirmation = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            operation=operation,
            summary=summary,
            risk_level=risk_level,
            status="pending",
            request_payload=request_payload,
            expires_at=expires_at,
            executed_at=None,
        )
        self.confirmations.append(confirmation)
        return confirmation


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @agent_tool(
        name="test.echo",
        summary="Echo",
        input_model=EchoInput,
        registry=registry,
    )
    async def echo(context, data):
        return {"value": data.value, "user_id": str(context.user_id)}

    @agent_tool(
        name="test.admin_echo",
        summary="Admin echo",
        input_model=EchoInput,
        required_roles=("admin",),
        registry=registry,
    )
    async def admin_echo(context, data):
        return {"value": data.value}

    @agent_tool(
        name="test.write_echo",
        summary="Write echo",
        input_model=EchoInput,
        write=True,
        registry=registry,
    )
    async def write_echo(context, data):
        return {"value": data.value, "confirmation_id": str(context.confirmation_id)}

    @agent_tool(
        name="test.human_decision",
        summary="Human decision",
        input_model=EchoInput,
        write=True,
        risk_level="high",
        human_decision_required=True,
        registry=registry,
    )
    async def human_decision(context, data):
        return {"value": data.value}

    return registry


def test_agent_tool_rejects_duplicate_registration() -> None:
    registry = ToolRegistry()

    @agent_tool(name="test.dup", summary="Dup", registry=registry)
    async def first(context, data):
        return None

    with pytest.raises(ValueError):

        @agent_tool(name="test.dup", summary="Dup again", registry=registry)
        async def second(context, data):
            return None


@pytest.mark.anyio
async def test_unregistered_tool_returns_400() -> None:
    executor = ToolExecutor(registry=ToolRegistry(), repo=FakeRepo())

    with pytest.raises(HTTPException) as exc_info:
        await executor.execute(
            FakeDb(),
            request=AgentToolExecuteRequest(operation="missing.tool"),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_input_validation_failure_returns_invalid_request_response() -> None:
    repo = FakeRepo()
    executor = ToolExecutor(registry=build_registry(), repo=repo)

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(operation="test.echo"),
    )

    assert response.ok is False
    assert response.meta["validation"] == "failed"
    assert repo.tool_calls[0].status == "invalid_request"


@pytest.mark.anyio
async def test_permission_denied_returns_403() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), role="user", is_deleted=False)
    executor = ToolExecutor(registry=build_registry(), repo=FakeRepo())

    with pytest.raises(HTTPException) as exc_info:
        await executor.execute(
            FakeDb(user=user),
            request=AgentToolExecuteRequest(
                operation="test.admin_echo",
                params={"value": "x"},
                context={"user_id": str(user.id)},
            ),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_read_tool_executes_and_writes_audit() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), role="user", is_deleted=False)
    db = FakeDb(user=user)
    repo = FakeRepo()
    executor = ToolExecutor(registry=build_registry(), repo=repo)

    response = await executor.execute(
        db,
        request=AgentToolExecuteRequest(
            operation="test.echo",
            params={"value": "ok"},
            context={"user_id": str(user.id)},
        ),
    )

    assert response.ok is True
    assert response.data["value"] == "ok"
    assert repo.tool_calls[0].status == "succeeded"
    assert db.added[0].action == "agent_tool_execute"


@pytest.mark.anyio
async def test_write_tool_requires_confirmation_then_executes() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), role="user", is_deleted=False)
    db = FakeDb(user=user)
    repo = FakeRepo()
    executor = ToolExecutor(registry=build_registry(), repo=repo)
    request = AgentToolExecuteRequest(
        operation="test.write_echo",
        params={"value": "draft"},
        context={"user_id": str(user.id)},
    )

    response = await executor.execute(db, request=request)
    confirmed = await executor.execute_confirmed(
        db,
        request=request,
        current_user=user,
        confirmation=repo.confirmations[0],
    )

    assert response.requires_confirmation is True
    assert repo.tool_calls[0].status == "confirmation_required"
    assert confirmed.ok is True
    assert confirmed.data["value"] == "draft"


@pytest.mark.anyio
async def test_human_decision_tool_returns_policy_refusal() -> None:
    executor = ToolExecutor(registry=build_registry(), repo=FakeRepo())

    response = await executor.execute(
        FakeDb(),
        request=AgentToolExecuteRequest(
            operation="test.human_decision",
            params={"value": "approve"},
        ),
    )

    assert response.ok is False
    assert response.meta["policy"] == "human_decision_required"
