from fastapi.routing import APIRoute

from app.main import app
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry


def _paths(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    }


def test_warehouse_page_and_legacy_feishu_routes_are_mounted() -> None:
    paths = _paths("/api/v1/warehouse")

    assert "/api/v1/warehouse/material-pages/{page_key}" in paths
    assert "/api/v1/warehouse/feishu/tables" in paths
    assert "/api/v1/warehouse/feishu/tables/{table_id}/records" in paths
    assert "/api/v1/warehouse/feishu/tables/{table_id}/sync" in paths
    assert "/api/v1/warehouse/ai/summary" in paths


def test_warehouse_agent_operations_use_reviewed_page_bindings() -> None:
    ensure_agent_tools_registered()

    expected = {
        "warehouse.list_raw_materials": "warehouse:materials:raw-summary",
        "warehouse.list_packaging_materials": "warehouse:materials:packaging-summary",
        "warehouse.list_products": "warehouse:product-inventory:product-summary",
        "warehouse.list_feishu_tables": "warehouse:warehouse-settings",
        "warehouse.get_feishu_table_records": "warehouse:warehouse-settings",
    }
    for operation, page_key in expected.items():
        assert tool_registry.require(operation).page_keys == (page_key,)
