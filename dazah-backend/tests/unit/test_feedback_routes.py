from app.main import app
from app.platform.system.feedback_api import router


def test_feedback_public_contract_is_mounted_in_application() -> None:
    actual = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or [])
    }
    for route in router.routes:
        for method in route.methods:
            assert (f"/api/v1{route.path}", method) in actual
