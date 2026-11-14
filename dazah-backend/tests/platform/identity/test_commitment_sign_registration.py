"""承诺签署免登端点登记守护：契约豁免/公开前缀/挂载一致。"""

from fastapi.routing import APIRoute

from app.main import app as api_app
from app.platform.identity.safety_api_contract import SAFETY_SIGNATURE_ROUTES

EXPECTED = {
    ("GET", "/api/v1/safety/commitment-sign/{token}"),
    ("POST", "/api/v1/safety/commitment-sign"),
}


def test_commitment_sign_routes_in_signature_boundary():
    """免登签署端点必须登记 SAFETY_SIGNATURE_ROUTES（HMAC token 自鉴权协议边界）。"""
    assert EXPECTED <= set(SAFETY_SIGNATURE_ROUTES)


def test_commitment_sign_routes_mounted_and_public():
    """端点真实挂载，且路径在公开前缀放行（token 自鉴权）。"""
    from app.platform.identity import rbac

    mounted = {
        (method, route.path)
        for route in api_app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert EXPECTED <= mounted, "承诺签署端点未挂载"
    prefixes = rbac.PUBLIC_PATH_PREFIXES
    assert any(
        str(p).rstrip("/") == "/api/v1/safety/commitment-sign" for p in prefixes
    ), "公开前缀缺 commitment-sign"
