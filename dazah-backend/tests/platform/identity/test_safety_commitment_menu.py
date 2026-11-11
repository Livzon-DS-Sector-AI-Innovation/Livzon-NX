"""安全承诺页面的菜单种子与权限目录一致性守护。"""

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_policy import get_page_definition


def test_safety_commitment_menu_directly_after_overview() -> None:
    safety = next(menu for menu in SEED_MENUS if menu["key"] == "safety")
    top_keys = [
        entry.get("key")
        for entry in safety.get("children", [])
        if entry.get("path")
    ]
    # 一级页面：紧随「安全总览」之后的叶子节点
    assert top_keys[:2] == ["overview", "safety-commitment"]

    page = get_page_definition("safety:safety-commitment")
    assert page is not None
    assert page.route_path == "/safety/safety-commitment"
    assert page.module_code == "safety"


def test_safety_commitment_api_bindings_registered() -> None:
    from app.platform.identity.page_policy import (
        PAGE_API_BINDINGS,
        api_binding_for_route,
    )

    paths = {
        (binding.method, binding.route_path)
        for binding in PAGE_API_BINDINGS
        if binding.route_path.startswith("/api/v1/safety/safety-commitment")
    }
    assert ("GET", "/api/v1/safety/safety-commitments/today") in paths
    assert (
        "PUT",
        "/api/v1/safety/safety-commitments/{report_id}",
    ) in paths
    assert (
        "POST",
        "/api/v1/safety/safety-commitments/{report_id}/publish",
    ) in paths
    assert (
        "POST",
        "/api/v1/safety/safety-commitments/{report_id}/risk-assessment",
    ) in paths
    assert ("GET", "/api/v1/safety/safety-commitment-cards") in paths
    assert ("DELETE", "/api/v1/safety/safety-commitment-cards/{card_id}") in paths

    # 重复绑定会让 api_binding_for_route fail closed，守护关键路由可解析
    binding = api_binding_for_route(
        "PUT", "/api/v1/safety/safety-commitments/{report_id}"
    )
    assert binding is not None
    assert binding.page_keys == ("safety:safety-commitment",)


def test_work_permit_settings_binding_not_duplicated() -> None:
    """守护未提交改动的回归：work-permit-settings 重复绑定会 fail closed。"""
    from app.platform.identity.page_policy import PAGE_API_BINDINGS

    settings_bindings = [
        binding
        for binding in PAGE_API_BINDINGS
        if binding.route_path == "/api/v1/safety/work-permit-settings"
    ]
    assert len(settings_bindings) == 2  # GET + PUT 各一条

    from app.platform.identity.page_policy import api_binding_for_route

    resolved = api_binding_for_route("GET", "/api/v1/safety/work-permit-settings")
    assert resolved is not None
