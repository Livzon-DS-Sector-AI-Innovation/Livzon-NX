from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.page_policy import tool_page_bindings


def test_tool_page_projection_matches_live_registry():
    ensure_agent_tools_registered()
    projection = tool_page_bindings()
    assert projection is not None
    assert {item.name for item in projection} == {
        item.name for item in tool_registry.list()
    }
    for item in projection:
        spec = tool_registry.require(item.name)
        assert item.page_keys == spec.page_keys
        assert item.sensitive_action == spec.sensitive_action
        assert item.module_code == spec.module
