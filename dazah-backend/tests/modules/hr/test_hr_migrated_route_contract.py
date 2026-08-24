from fastapi.routing import APIRoute

from app.main import app


def _paths(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    }


def test_migrated_hr_contract_routes_are_mounted() -> None:
    paths = _paths("/api/v1/hr")

    assert "/api/v1/hr/contracts" in paths
    assert "/api/v1/hr/annual-training-plans/{plan_id}/attachments" in paths
    preview_path = "/api/v1/hr/annual-training-plan-attachments/{attachment_id}/preview"
    assert preview_path in paths
    assert "/api/v1/hr/training-attachment" in paths
    assert "/api/v1/hr/email/upload-offer-template" in paths
