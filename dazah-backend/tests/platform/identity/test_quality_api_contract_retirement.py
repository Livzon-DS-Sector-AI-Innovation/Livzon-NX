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
