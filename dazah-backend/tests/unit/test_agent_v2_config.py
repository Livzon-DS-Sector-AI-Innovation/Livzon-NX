import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_agent_backend_v2_url_is_normalized() -> None:
    settings = Settings(
        HERMES_AGENT_V2_URL="http://hermes-lite:8100/v2/agent/runs/",
    )

    assert settings.HERMES_AGENT_V2_URL.endswith("/v2/agent/runs")


def test_agent_backend_v1_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="AgentBackend V2"):
        Settings(HERMES_AGENT_V2_URL="http://hermes-lite:8100/v1/chat")
