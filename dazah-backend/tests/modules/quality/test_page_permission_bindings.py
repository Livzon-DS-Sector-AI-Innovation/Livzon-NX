from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.modules.quality.page_access import DEVIATION_LEDGER_PAGE
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    api_binding_for_route,
    page_api_catalog_gaps,
    page_key_for_route,
)


def test_deviation_read_tools_require_the_deviation_page():
    ensure_agent_tools_registered()
    for operation in (
        "quality.list_deviations",
        "quality.get_deviation",
        "quality.get_related_capas",
    ):
        tool = tool_registry.require(operation)
        assert tool.page_keys == (DEVIATION_LEDGER_PAGE,)
        assert not tool.write
        assert tool.sensitive_action is None


def test_deviation_write_tools_use_reviewed_leaf_without_relaxing_confirmation():
    ensure_agent_tools_registered()
    for operation in ("quality.create_deviation", "quality.update_deviation"):
        tool = tool_registry.require(operation)
        assert tool.page_keys == (DEVIATION_LEDGER_PAGE,)
        assert tool.write and tool.risk_level == "medium"
        assert tool.confirmation_required
        binding = api_binding_for_route(tool.method, "/api/v1" + tool.path)
        assert binding and binding.permission == "operate"


def test_ledger_contract_keeps_unreviewed_workflows_closed():
    page = PAGES_BY_KEY[DEVIATION_LEDGER_PAGE]
    assert "self" not in page.supported_scope_types
    actions = {action.key: action.name for action in page.sensitive_actions}
    assert actions["delete"] == "删除偏差记录"
    assert actions["sensitive_export"] == "导出偏差台账"
    assert (
        api_binding_for_route(
            "GET", "/api/v1/quality/deviations/export"
        ).sensitive_action
        == "sensitive_export"
    )
    assert (
        api_binding_for_route(
            "POST", "/api/v1/quality/deviations/batch-delete"
        ).sensitive_action
        == "delete"
    )
    assert page_api_catalog_gaps("quality")


def test_deviation_auxiliary_routes_do_not_authorize_sibling_pages():
    assert page_key_for_route("/quality/deviations/new") == DEVIATION_LEDGER_PAGE
    assert (
        page_key_for_route("/quality/deviations/00000000-0000-0000-0000-000000000001")
        == DEVIATION_LEDGER_PAGE
    )
    assert (
        page_key_for_route("/quality/deviations/records")
        == "quality:deviations:deviation-records"
    )
    assert (
        page_key_for_route(
            "/quality/deviations/00000000-0000-0000-0000-000000000001/ai"
        )
        != DEVIATION_LEDGER_PAGE
    )
