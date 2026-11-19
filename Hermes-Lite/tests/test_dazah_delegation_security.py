"""User delegation stays in trusted tool context, outside model-visible payloads."""

import uuid

import pytest

from services.dazah_agent_service import AgentBackendV2Request


@pytest.mark.parametrize("delegation", [
    "synthetic-delegation",
    # Simulated browser sessions carry extra signed claims. Hermes treats the JWT as opaque.
    "synthetic-header." + "a" * 700 + ".synthetic-signature",
])
def test_delegation_is_forwarded_to_tool_context_but_not_serialized(delegation):
    payload = AgentBackendV2Request.model_validate({
        "protocol_version": "2.0", "run_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()), "session_id": "web:" + str(uuid.uuid4()),
        "subject": {"user_id": str(uuid.uuid4()), "tenant_id": "factory",
                    "source": "web", "delegation_token": delegation},
        "source": {"platform": "web"}, "message": "test",
    })
    assert payload.context["delegation_token"] == delegation
    assert delegation not in payload.model_dump_json()
    assert delegation not in repr(payload)
