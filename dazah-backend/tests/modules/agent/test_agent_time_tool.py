from datetime import datetime

import pytest

from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry


@pytest.mark.anyio
async def test_get_current_time_tool_returns_precise_schedule_time() -> None:
    ensure_agent_tools_registered()
    spec = tool_registry.require("agent.get_current_time")

    result = await spec.handler(object(), spec.input_model())  # type: ignore[arg-type]

    assert spec.write is False
    assert spec.risk_level == "medium"
    assert result["timezone"] == "Asia/Shanghai"
    assert result["cron_timezone"] == "Asia/Shanghai"
    assert result["utc_offset"] == "+08:00"
    assert isinstance(result["unix_seconds"], int)
    assert isinstance(result["unix_milliseconds"], int)
    assert result["unix_milliseconds"] >= result["unix_seconds"] * 1000
    assert datetime.fromisoformat(result["local_iso"]).tzinfo is not None
    assert datetime.fromisoformat(result["utc_iso"]).tzinfo is not None
    assert result["date"] == result["local_iso"][:10]
