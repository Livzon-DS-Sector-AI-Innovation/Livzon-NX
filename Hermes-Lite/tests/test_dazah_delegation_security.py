"""User delegation stays in trusted tool context, outside model-visible payloads."""

import uuid

from services.dazah_agent_service import AgentBackendV2Request


def test_delegation_is_forwarded_to_tool_context_but_not_serialized():
    payload = AgentBackendV2Request.model_validate({
        "protocol_version": "2.0", "run_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()), "session_id": "web:" + str(uuid.uuid4()),
        "subject": {"user_id": str(uuid.uuid4()), "tenant_id": "factory",
                    "source": "web", "delegation_token": "synthetic-delegation"},
        "source": {"platform": "web"}, "message": "test",
    })
    assert payload.context["delegation_token"] == "synthetic-delegation"
    assert "synthetic-delegation" not in payload.model_dump_json()
    assert "synthetic-delegation" not in repr(payload)
