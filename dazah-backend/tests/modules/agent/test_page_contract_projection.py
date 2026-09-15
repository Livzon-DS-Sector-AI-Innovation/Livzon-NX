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


def test_warehouse_tools_use_reviewed_page_bindings():
    ensure_agent_tools_registered()

    expected = {
        "warehouse.list_raw_materials": (
            ("warehouse:materials:raw-summary",),
            None,
        ),
        "warehouse.list_packaging_materials": (
            ("warehouse:materials:packaging-summary",),
            None,
        ),
        "warehouse.list_products": (
            ("warehouse:product-inventory:product-summary",),
            None,
        ),
        "warehouse.list_feishu_tables": (
            ("warehouse:warehouse-settings",),
            None,
        ),
        "warehouse.get_feishu_table_records": (
            ("warehouse:warehouse-settings",),
            None,
        ),
        "warehouse.get_feishu_ws_status": (
            ("warehouse:warehouse-settings",),
            None,
        ),
        "warehouse.sync_feishu_table": (
            ("warehouse:warehouse-settings",),
            "sync_config",
        ),
        "warehouse.restart_feishu_ws": (
            ("warehouse:warehouse-settings",),
            "sync_config",
        ),
    }
    for operation, (page_keys, sensitive_action) in expected.items():
        spec = tool_registry.require(operation)
        assert spec.page_keys == page_keys
        assert spec.sensitive_action == sensitive_action
