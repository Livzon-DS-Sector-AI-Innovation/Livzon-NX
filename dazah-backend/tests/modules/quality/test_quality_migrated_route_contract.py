from collections import Counter

from fastapi.routing import APIRoute

from app.main import app


def _paths(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    }


def test_migrated_quality_submodules_are_mounted() -> None:
    paths = _paths("/api/v1/quality")

    assert "/api/v1/quality/document-catalog/import" in paths
    assert "/api/v1/quality/document-entries/{entry_id}/attachments" in paths
    assert "/api/v1/quality/instruments/equipment" in paths
    assert "/api/v1/quality/oos-oot/oot-limit-products" in paths
    assert "/api/v1/quality/cpv/products" in paths


def test_quality_routes_do_not_register_duplicate_method_path_pairs() -> None:
    keys = [
        (route.path, method)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/quality")
        for method in route.methods or set()
    ]

    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    assert duplicates == []
