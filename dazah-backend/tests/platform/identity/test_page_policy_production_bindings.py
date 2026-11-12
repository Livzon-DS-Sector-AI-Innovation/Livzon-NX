"""生产模块页面绑定抽查：新增端点必须完成页面权限登记。"""

from app.platform.identity import page_policy


def test_seed_culture_person_monthly_binding_registered() -> None:
    """人员月度统计端点登记在菌种/车间与概览页（query 口径）。"""
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/production/seed-cultures/person-monthly"
    )
    assert binding is not None
    assert binding.permission == "query"
    assert "production:overview" in binding.page_keys
    assert any(
        key.startswith("production:batches:workshop-")
        for key in binding.page_keys
    )
    assert binding.scope_adapter == "production.workshop"


def test_seed_cultures_list_binding_unchanged() -> None:
    """既有列表端点绑定不受新增端点影响。"""
    binding = page_policy.api_binding_for_route(
        "GET", "/api/v1/production/seed-cultures"
    )
    assert binding is not None
    assert binding.permission == "query"
