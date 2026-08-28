from fastapi.routing import APIRoute

from app.main import app


def _paths(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    }


def test_migrated_registration_and_legacy_routes_are_mounted() -> None:
    paths = _paths("/api/v1/registration")

    assert "/api/v1/registration/project-ledger/workbook/import" in paths
    assert "/api/v1/registration/certificate-management/workbook/import" in paths
    assert "/api/v1/registration/knowledge/articles/{article_id}/attachments" in paths
    assert "/api/v1/registration/reference-standards/generate" in paths
    assert "/api/v1/registration/supplementary-replies/generate" in paths
    assert "/api/v1/registration/validation-audit/tasks/{task_id}/files" in paths
