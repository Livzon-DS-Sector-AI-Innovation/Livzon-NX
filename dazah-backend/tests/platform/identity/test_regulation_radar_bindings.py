"""法规雷达接口的平台权限登记断言（页面绑定与敏感操作）。"""

from app.platform.identity.page_policy import (
    _sensitive_actions,
    api_binding_for_route,
)

_KNOWLEDGE_PAGE = "safety:regulation-info:knowledge-base"
_SETTINGS_PAGE = "safety:system-config:safety-feishu-settings"


def test_radar_run_route_bound_to_knowledge_page_as_sensitive_action() -> None:
    """手动扫描绑定知识库页，并作为 sync_config 敏感操作登记。"""
    binding = api_binding_for_route(
        "POST", "/api/v1/safety/knowledge-articles/radar/run"
    )
    assert binding is not None
    assert binding.page_keys == (_KNOWLEDGE_PAGE,)
    assert binding.permission == "operate"
    assert binding.sensitive_action == "sync_config"


def test_radar_notify_test_route_bound_to_settings_page() -> None:
    """通知测试绑定飞书设置页（凭证与通知目标均在该页维护）。"""
    binding = api_binding_for_route(
        "POST", "/api/v1/safety/knowledge-articles/radar/notify/test"
    )
    assert binding is not None
    assert binding.page_keys == (_SETTINGS_PAGE,)
    assert binding.permission == "operate"
    assert binding.sensitive_action == "sync_config"


def test_radar_run_queries_bound_to_knowledge_page() -> None:
    """批次列表与详情为知识库页只读查询。"""
    listing = api_binding_for_route(
        "GET", "/api/v1/safety/knowledge-articles/radar/runs"
    )
    detail = api_binding_for_route(
        "GET", "/api/v1/safety/knowledge-articles/radar/runs/{run_id}"
    )
    for binding in (listing, detail):
        assert binding is not None
        assert binding.page_keys == (_KNOWLEDGE_PAGE,)


def test_knowledge_page_registers_radar_sensitive_action() -> None:
    """知识库页敏感操作包含 sync_config（雷达扫描与镜像同步共用）。"""
    actions = _sensitive_actions(_KNOWLEDGE_PAGE, "/safety/knowledge-base", "知识库")
    keys = {action.key for action in actions}
    assert "sync_config" in keys
