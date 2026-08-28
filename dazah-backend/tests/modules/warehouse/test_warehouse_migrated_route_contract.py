from fastapi.routing import APIRoute

from app.main import app


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
