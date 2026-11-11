"""图表警戒线接口的页面权限登记回归。

平台规则：新增业务接口必须完成页面权限登记；写接口（PUT）必须挂 operate 口径。
本文件锁定 GET/PUT /production/chart-thresholds 的登记不被误删或降级。
"""

from __future__ import annotations

from app.platform.identity import page_policy


def test_chart_thresholds_get_registered_as_query() -> None:
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/production/chart-thresholds"
    )
    assert binding is not None, "GET /chart-thresholds 未登记页面权限"
    assert "production:overview" in binding.page_keys
    assert binding.permission == "query"


def test_chart_thresholds_put_registered_as_operate() -> None:
    binding = page_policy.api_binding_for_route(
        "PUT", "/api/v1/production/chart-thresholds"
    )
    assert binding is not None, "PUT /chart-thresholds 未登记页面权限"
    assert "production:overview" in binding.page_keys
    # 平台规则：业务写入必须要求操作权限
    assert binding.permission == "operate"


def test_production_catalog_has_no_gaps() -> None:
    assert page_policy.page_api_catalog_gaps("production") == []
