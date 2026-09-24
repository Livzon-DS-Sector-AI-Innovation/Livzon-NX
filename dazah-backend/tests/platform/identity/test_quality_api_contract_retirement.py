"""质量 API 契约退休：旧飞书 CAPA 台账/同步路由不再登记为已评审路由。"""

from app.platform.identity.quality_api_contract import QUALITY_REVIEWED_API_ROUTES


def test_retired_feishu_capa_routes_removed_from_reviewed_contract() -> None:
    routes = set(QUALITY_REVIEWED_API_ROUTES)
    for retired in (
        ("DELETE", "/api/v1/quality/feishu/capas/{record_id}"),
        ("GET", "/api/v1/quality/feishu/capas"),
        ("GET", "/api/v1/quality/feishu/capas/export"),
        ("GET", "/api/v1/quality/feishu/capas/{record_id}"),
        ("POST", "/api/v1/quality/capas/sync-from-feishu"),
        ("POST", "/api/v1/quality/feishu-sync/capas/{capa_id}"),
        ("POST", "/api/v1/quality/feishu-sync/deviations/{deviation_id}"),
        ("POST", "/api/v1/quality/feishu/capas"),
        ("PUT", "/api/v1/quality/feishu/capas/{record_id}"),
    ):
        assert retired not in routes, f"退休路由仍登记在评审契约: {retired}"


def test_due_status_route_registered_in_reviewed_contract() -> None:
    """变更行动计划到期状态接口必须登记为已评审路由（页面权限绑定依赖）。"""
    routes = set(QUALITY_REVIEWED_API_ROUTES)
    assert ("GET", "/api/v1/quality/change-action-plans/due-status") in routes


def test_due_status_route_binds_to_change_plans_and_ledgers() -> None:
    """到期状态接口同时被变更计划页与变更台账页读取，绑定两页。"""
    from app.platform.identity.page_policy import api_binding_for_route

    binding = api_binding_for_route(
        "GET", "/api/v1/quality/change-action-plans/due-status"
    )
    assert binding is not None
    assert set(binding.page_keys) == {
        "quality:change:change-action-plans",
        "quality:change:change-ledger",
        "quality:change:file-change-ledger",
    }
