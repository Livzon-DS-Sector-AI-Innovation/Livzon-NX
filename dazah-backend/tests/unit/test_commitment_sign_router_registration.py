"""公开路由挂载守护：承诺免登签署路由挂在主路由（token 自鉴权，不挂模块权限）。"""

from fastapi.routing import APIRoute

from app.api.router import api_router


def test_commitment_sign_router_mounted_on_public_entry():
    """承诺签署端点必须经公共路由入口挂载（不走模块权限路由）。"""
    mounted = {
        (method, route.path)
        for route in api_router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert {
        ("GET", "/safety/commitment-sign/{token}"),
        ("POST", "/safety/commitment-sign"),
    } <= mounted
