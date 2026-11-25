"""Page permission registration for the material price query page."""

import json
from pathlib import Path

from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    api_binding_for_route,
    page_key_for_route,
)

LIFECYCLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "platform"
    / "identity"
    / "page_permission_lifecycle.json"
)


def test_material_price_page_is_registered_with_all_scope() -> None:
    page = PAGES_BY_KEY.get("purchasing:material-price")
    assert page is not None
    assert page.module_code == "procurement"
    assert page.route_path == "/purchasing/material-price"
    # 价格数据无部门归属，页面只支持全部数据范围。
    assert tuple(page.supported_scope_types) == ("all",)
    assert (
        page_key_for_route("/purchasing/material-price")
        == "purchasing:material-price"
    )


def test_material_price_api_bindings_require_query_permission() -> None:
    for route_path in (
        "/api/v1/procurement/material-prices",
        "/api/v1/procurement/material-prices/{material_code}",
    ):
        binding = api_binding_for_route("GET", route_path)
        assert binding is not None, route_path
        assert binding.page_keys == ("purchasing:material-price",)
        assert binding.permission == "query"
        assert binding.sensitive_action is None


def test_material_price_page_has_active_lifecycle_entry() -> None:
    ledger = json.loads(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    entry = ledger["pages"]["purchasing:material-price"]
    assert entry["status"] == "active"
    assert entry["module_code"] == "procurement"
    assert entry["route_path"] == "/purchasing/material-price"
    assert entry["actions"] == {}
