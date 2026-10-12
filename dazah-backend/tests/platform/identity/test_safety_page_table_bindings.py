"""页面镜像接口的平台权限登记断言（页面绑定、敏感操作与生命周期账本）。"""

from app.modules.safety.page_tables import PAGE_TABLE_DEFINITIONS, get_page_table
from app.platform.identity.page_lifecycle import load_ledger
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    _sensitive_actions,
    api_binding_for_route,
    page_lifecycle_errors,
)

_PAGE = "safety:risk-hazard:hazard-inspection:hazard-duty"
_SETTINGS_PAGE = "safety:system-config:safety-feishu-settings"


def test_page_table_registry_matches_registered_page_definition() -> None:
    """注册表里的页面标识必须与菜单派生的页面定义一致，否则权限绑定无从生效。"""
    assert len(PAGE_TABLE_DEFINITIONS) == 1
    definition = get_page_table(_PAGE)
    assert definition is not None
    assert definition.page_name == "24小时值班隐患"
    assert definition.route_path == "/safety/hazard-duty"

    page = PAGES_BY_KEY[_PAGE]
    assert page.module_code == "safety"
    assert page.route_path == definition.route_path
    assert page_lifecycle_errors(page) == []


def test_registry_lookup_returns_none_for_unknown_page() -> None:
    assert get_page_table("safety:not:registered") is None


def test_config_routes_bound_to_feishu_settings_page() -> None:
    """绑定维护归飞书设置页，且作为 sync_config 敏感操作登记。"""
    routes = [
        ("GET", "/api/v1/safety/page-feishu-configs"),
        ("PUT", "/api/v1/safety/page-feishu-configs/{page_key}"),
        ("POST", "/api/v1/safety/page-feishu-configs/{page_key}/test"),
        ("POST", "/api/v1/safety/page-feishu-configs/resolve"),
    ]
    for method, path in routes:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert binding.page_keys == (_SETTINGS_PAGE,)
        assert binding.scope_adapter == "not_applicable"
        if method == "GET":
            assert binding.permission == "query"
            assert binding.sensitive_action is None
        else:
            assert binding.permission == "operate"
            assert binding.sensitive_action == "sync_config"


def test_data_routes_bound_to_duty_hazard_page() -> None:
    routes = [
        ("GET", "/api/v1/safety/page-tables/{page_key}/records", "query"),
        ("GET", "/api/v1/safety/page-tables/{page_key}/stats", "query"),
        ("PUT", "/api/v1/safety/page-tables/{page_key}/records/{record_id}", "operate"),
        (
            "POST",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}",
            "operate",
        ),
        (
            "GET",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/content",
            "query",
        ),
        (
            "GET",
            "/api/v1/safety/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/thumbnail",
            "query",
        ),
    ]
    for method, path, permission in routes:
        binding = api_binding_for_route(method, path)
        assert binding is not None, f"{method} {path} 未登记页面绑定"
        assert binding.page_keys == (_PAGE,)
        assert binding.permission == permission
        assert binding.scope_adapter == "not_applicable"
        # 该页敏感动作为空集：绑定的动作必须也为空，否则 _api_binding_errors 会拒绝
        assert binding.sensitive_action is None


def test_duty_hazard_page_has_no_sensitive_actions() -> None:
    """页面名与路径不含台账/设置/导入等关键词，推导出的敏感动作为空。"""
    actions = _sensitive_actions(_PAGE, "/safety/hazard-duty", "24小时值班隐患")
    assert actions == ()


def test_duty_hazard_page_registered_in_lifecycle_ledger() -> None:
    ledger = load_ledger()
    entry = ledger["pages"][_PAGE]
    assert entry["status"] == "active"
    assert entry["module_code"] == "safety"
    assert entry["route_path"] == "/safety/hazard-duty"
    assert entry["actions"] == {}
