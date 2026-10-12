from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.shared.module_registry import AGENT_TOOL_PROVIDER_MODULES, MODULES_BY_CODE


def test_requested_modules_are_discovered_from_registry():
    ensure_agent_tools_registered()
    for code in (
        "production",
        "warehouse",
        "procurement",
        "hr",
        "registration",
        "quality",
    ):
        provider = f"app.modules.{code}.agent_tools"
        assert MODULES_BY_CODE[code].agent_tools_module == provider
        assert provider in AGENT_TOOL_PROVIDER_MODULES
        specs = [spec for spec in tool_registry.list() if spec.module == code]
        assert specs
        assert all(spec.page_keys for spec in specs)
        assert all(spec.output_schema for spec in specs)
        assert all(
            not spec.workflow_allowed for spec in specs if spec.human_decision_required
        )
