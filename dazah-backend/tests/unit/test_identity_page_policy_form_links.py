"""仓储表单链接新端点的页面权限绑定测试。

- /material-pages/{page_key}/form-links 必须覆盖全部台账页别名（换 Base 不影响）；
- /home-quick-form-links 绑定快捷卡目标台账页（首页自身不是注册业务页）。
"""

from app.platform.identity.page_policy import (
    WAREHOUSE_MATERIAL_PAGE_ALIASES,
    api_binding_for_route,
    canonical_page_key,
)


def test_material_page_form_links_binding_covers_all_pages() -> None:
    """form-links 端点与 material-pages GET 使用同一组台账页绑定。"""
    binding = api_binding_for_route(
        "GET", "/api/v1/warehouse/material-pages/{page_key}/form-links"
    )
    assert binding is not None
    assert binding.page_keys == tuple(WAREHOUSE_MATERIAL_PAGE_ALIASES)
    for key in WAREHOUSE_MATERIAL_PAGE_ALIASES:
        assert canonical_page_key(key) in binding.page_keys, key


def test_home_quick_form_links_binding_targets_quick_card_pages() -> None:
    """首页快捷表单卡端点绑定 7 个目标台账页（含入库总账上下文页）。"""
    binding = api_binding_for_route("GET", "/api/v1/warehouse/home-quick-form-links")
    assert binding is not None
    assert binding.permission == "query"
    assert "warehouse:materials:inbound-ledger" in binding.page_keys
    assert len(binding.page_keys) == 7
