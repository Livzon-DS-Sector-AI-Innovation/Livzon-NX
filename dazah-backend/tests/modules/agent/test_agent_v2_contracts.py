import uuid

import pytest
from pydantic import ValidationError

from app.modules.agent.schemas import (
    AgentBackendV2Event,
    AgentBackendV2Request,
    AgentToolExecuteRequest,
)
from app.shared.module_registry import AGENT_TOOL_PROVIDER_MODULES


def _subject() -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "user_id": str(uuid.uuid4()),
        "source": "feishu",
        "platform": "feishu",
        "app_fingerprint": "cli_test",
        "external_user_id": "ou_test",
    }


def test_agent_backend_v2_rejects_caller_context_and_requires_subject() -> None:
    with pytest.raises(ValidationError):
        AgentBackendV2Request.model_validate(
            {
                "message": "hello",
                "conversation_id": "chat",
                "subject": _subject(),
                "source": {"channel": "feishu"},
                "context": {"user_id": str(uuid.uuid4())},
            }
        )

    with pytest.raises(ValidationError):
        AgentBackendV2Request.model_validate(
            {
                "message": "hello",
                "conversation_id": "chat",
                "source": {"channel": "feishu"},
            }
        )


def test_tool_execute_rejects_old_context_identity_shape() -> None:
    with pytest.raises(ValidationError):
        AgentToolExecuteRequest.model_validate(
            {
                "operation": "agent.get_current_time",
                "context": {"user_id": str(uuid.uuid4())},
            }
        )


def test_v2_event_requires_sequence_and_trace_envelope() -> None:
    event = AgentBackendV2Event(
        trace_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        sequence=1,
        type="accepted",
        data={"status": "accepted"},
    )

    assert event.sequence == 1
    assert event.event_id


def test_module_registry_declares_provider_modules() -> None:
    assert "app.modules.energy.agent_tools" in AGENT_TOOL_PROVIDER_MODULES
    assert "app.modules.warehouse.agent_tools" in AGENT_TOOL_PROVIDER_MODULES
    assert "app.modules.procurement.agent_tools" in AGENT_TOOL_PROVIDER_MODULES
    assert "app.modules.quality.agent_tools" in AGENT_TOOL_PROVIDER_MODULES
