"""仓储子表读取接口必须登记在仓储设置页绑定（wiki 链接解析依赖）。"""

from app.platform.identity.page_policy import api_binding_for_route


def test_warehouse_page_feishu_config_tables_route_is_bound() -> None:
    binding = api_binding_for_route(
        "GET", "/api/v1/warehouse/page-feishu-configs/tables"
    )
    assert binding is not None
    assert binding.permission == "query"
    assert set(binding.page_keys) == {"warehouse:warehouse-settings"}
