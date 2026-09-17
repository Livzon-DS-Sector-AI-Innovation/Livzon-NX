from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    QUALITY_PRODUCT_PAGES,
    api_binding_for_route,
)


def test_quality_agent_tools_project_reviewed_page_contracts():
    ensure_agent_tools_registered()

    quality_tools = [
        spec for spec in tool_registry.list() if spec.module == "quality"
    ]

    assert quality_tools
    assert all(spec.page_keys for spec in quality_tools)
    for spec in quality_tools:
        for page_key in spec.page_keys:
            assert page_key in PAGES_BY_KEY

        binding = api_binding_for_route(spec.method, "/api/v1" + spec.path)
        if binding is not None:
            assert spec.page_keys == binding.page_keys
            assert spec.sensitive_action == binding.sensitive_action


def test_quality_agent_tool_decorator_keeps_explicit_contracts():
    ensure_agent_tools_registered()

    cpv = tool_registry.require("quality.create_cpv_product")
    assert cpv.page_keys == QUALITY_PRODUCT_PAGES
    assert cpv.sensitive_action is None

    feishu_pull = tool_registry.require("quality.pull_feishu_validations")
    assert feishu_pull.page_keys == ("quality:validation:validation-plans",)
    assert feishu_pull.sensitive_action == "sync_config"
