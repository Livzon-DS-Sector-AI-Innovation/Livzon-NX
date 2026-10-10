"""安全模块飞书设置页面与知识库同步权限的平台登记断言。"""

from app.platform.identity.page_policy import api_binding_for_route


def test_safety_feishu_settings_routes_bound_to_settings_page() -> None:
    """飞书设置页接口绑定到 safety:system-config:safety-feishu-settings。"""
    binding = api_binding_for_route(
        "GET", "/api/v1/safety/feishu-settings/app"
    )
    assert binding is not None
    assert binding.page_keys == ("safety:system-config:safety-feishu-settings",)


def test_knowledge_base_page_owns_sync_config_sensitive_action() -> None:
    """知识库页 sync_config 为敏感操作（触发飞书镜像同步）。"""
    from app.platform.identity.page_policy import _sensitive_actions

    actions = _sensitive_actions(
        "safety:regulation-info:knowledge-base",
        "/safety/knowledge-base",
        "知识库",
    )
    keys = {action.key for action in actions}
    assert "sync_config" in keys
