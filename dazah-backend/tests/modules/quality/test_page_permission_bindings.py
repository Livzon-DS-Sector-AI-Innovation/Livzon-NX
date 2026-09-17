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


def test_all_quality_agent_tools_have_reviewed_page_contracts():
    ensure_agent_tools_registered()
    tools = [spec for spec in tool_registry.list() if spec.module == "quality"]

    assert tools
    assert not [spec.name for spec in tools if not spec.page_keys]
    for spec in tools:
        binding = api_binding_for_route(spec.method, "/api/v1" + spec.path)
        if binding is not None:
            assert spec.page_keys == binding.page_keys
            assert spec.sensitive_action == binding.sensitive_action
        for page_key in spec.page_keys:
            page = PAGES_BY_KEY[page_key]
            if spec.sensitive_action:
                assert spec.sensitive_action in {
                    action.key for action in page.sensitive_actions
                }


def test_ledger_contract_covers_all_reviewed_workflows():
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
    assert page_api_catalog_gaps("quality") == []


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


def test_inspection_dashboards_and_equipment_import_use_live_menu_leaves():
    inventory = "quality:inspection:inspection-items:inspection-items-inventory"
    equipment = (
        "quality:inspection:inspection-instruments:inspection-instruments-equipment"
    )
    item_dashboard = api_binding_for_route("GET", "/api/v1/quality/items/dashboard")
    assert item_dashboard is not None
    assert item_dashboard.page_keys == (inventory,)

    instrument_dashboard = api_binding_for_route(
        "GET", "/api/v1/quality/instruments/dashboard"
    )
    assert instrument_dashboard is not None
    assert equipment in instrument_dashboard.page_keys

    for method, path, action in (
        ("GET", "/api/v1/quality/instruments/equipment/{record_id}/profile", None),
        ("POST", "/api/v1/quality/instruments/equipment/import/preview", "bulk_import"),
        ("POST", "/api/v1/quality/instruments/equipment/import/confirm", "bulk_import"),
    ):
        binding = api_binding_for_route(method, path)
        assert binding is not None
        assert binding.page_keys == (equipment,)
        assert binding.sensitive_action == action

    maintenance_export = api_binding_for_route(
        "GET", "/api/v1/quality/instruments/maintenance/export"
    )
    assert maintenance_export is not None
    assert maintenance_export.page_keys == (
        "quality:inspection:inspection-instruments:inspection-instruments-maintenance",
    )
    assert maintenance_export.sensitive_action == "sensitive_export"
