"""Contract gates for the five-module migration compatibility surface."""

from __future__ import annotations

from collections import Counter

from fastapi.routing import APIRoute

from app.main import app


def _operation_pairs() -> set[tuple[str, str]]:
    return {
        (route.path, method.lower())
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }


# These are the legacy operations called out in the migration review.  They
# intentionally remain explicit: changing one requires a contract review,
# rather than silently making a client call disappear from OpenAPI.
LEGACY_HR_OPERATIONS = {
    ("/api/v1/hr/departure-records", "get"),
    ("/api/v1/hr/departure-records", "post"),
    ("/api/v1/hr/departure-records/sync-from-feishu", "post"),
    ("/api/v1/hr/departure-records/sync-status", "get"),
    ("/api/v1/hr/departure-records/{record_id}", "delete"),
    ("/api/v1/hr/departure-records/{record_id}", "get"),
    ("/api/v1/hr/departure-records/{record_id}", "put"),
    ("/api/v1/hr/new/departments", "get"),
    ("/api/v1/hr/new/departure-records", "get"),
    ("/api/v1/hr/new/employees", "get"),
    ("/api/v1/hr/new/offboarding-records", "get"),
    ("/api/v1/hr/new/onboarding-records", "get"),
    ("/api/v1/hr/onboarding-records", "get"),
    ("/api/v1/hr/onboarding-records/sync-from-feishu", "post"),
    ("/api/v1/hr/onboarding-records/sync-status", "get"),
    ("/api/v1/hr/onboarding-records/{record_id}", "get"),
    ("/api/v1/hr/training-notifications/send", "post"),
    ("/api/v1/hr/turnover-analysis", "get"),
}

LEGACY_QUALITY_OPERATIONS = {
    ("/api/v1/quality/oos-oot/records", "get"),
    ("/api/v1/quality/oos-oot/records", "post"),
    ("/api/v1/quality/oos-oot/records/{record_id}", "delete"),
    ("/api/v1/quality/oos-oot/records/{record_id}", "get"),
    ("/api/v1/quality/oos-oot/records/{record_id}", "put"),
    ("/api/v1/quality/oos-oot/records/{record_id}/sync-to-feishu", "post"),
    ("/api/v1/quality/oos-oot/oot-limits/products", "get"),
    ("/api/v1/quality/oos-oot/oot-limits/products", "post"),
    ("/api/v1/quality/oos-oot/oot-limits/products/{product_id}", "delete"),
    ("/api/v1/quality/oos-oot/oot-limits/products/{product_id}", "get"),
    ("/api/v1/quality/oos-oot/oot-limits/products/{product_id}", "put"),
    ("/api/v1/quality/oos-oot/oot-limits/products/{product_id}/sync-to-feishu", "post"),
}

LEGACY_WAREHOUSE_OPERATIONS = {
    ("/api/v1/warehouse/analysis/profiles", "post"),
    ("/api/v1/warehouse/analysis/profiles/{profile_id}", "get"),
    ("/api/v1/warehouse/analysis/profiles/{profile_id}/prompts", "get"),
    ("/api/v1/warehouse/analysis/profiles/{profile_id}/prompts", "post"),
    (
        "/api/v1/warehouse/analysis/profiles/{profile_id}/prompts/{prompt_id}/publish",
        "post",
    ),
    ("/api/v1/warehouse/analysis/profiles/{profile_id}/run", "post"),
    ("/api/v1/warehouse/analysis/runs/{run_id}", "get"),
    ("/api/v1/warehouse/analytics/query", "post"),
    ("/api/v1/warehouse/feishu-config", "get"),
    ("/api/v1/warehouse/feishu-config", "put"),
    ("/api/v1/warehouse/feishu-config/test", "post"),
    ("/api/v1/warehouse/feishu/roots", "get"),
    ("/api/v1/warehouse/feishu/roots", "post"),
    ("/api/v1/warehouse/feishu/roots/{root_id}", "delete"),
    ("/api/v1/warehouse/feishu/roots/{root_id}/discover", "post"),
    ("/api/v1/warehouse/feishu/ws/status", "get"),
    ("/api/v1/warehouse/page-data/{page_key}", "get"),
    ("/api/v1/warehouse/page-data/{page_key}", "put"),
    (
        "/api/v1/warehouse/page-data/{page_key}/{binding_id}/field-values/{field_id}",
        "get",
    ),
    ("/api/v1/warehouse/page-data/{page_key}/{binding_id}/record/{record_id}", "get"),
    (
        "/api/v1/warehouse/page-data/{page_key}/{binding_id}/record/{record_id}/attachments/{field_id}/{file_token}",
        "get",
    ),
    ("/api/v1/warehouse/page-data/{page_key}/{binding_id}/records", "get"),
}

REQUIRED_LEGACY_OPERATIONS = (
    LEGACY_HR_OPERATIONS | LEGACY_QUALITY_OPERATIONS | LEGACY_WAREHOUSE_OPERATIONS
)


def test_migration_legacy_operation_matrix_is_complete() -> None:
    assert len(LEGACY_HR_OPERATIONS) == 18
    assert len(LEGACY_QUALITY_OPERATIONS) == 12
    assert len(LEGACY_WAREHOUSE_OPERATIONS) == 22
    assert len(REQUIRED_LEGACY_OPERATIONS) == 52

    missing = REQUIRED_LEGACY_OPERATIONS - _operation_pairs()
    assert missing == set()


def test_migration_operation_pairs_are_unique() -> None:
    pairs = [
        (route.path, method.lower())
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith(
            (
                "/api/v1/quality",
                "/api/v1/registration",
                "/api/v1/hr",
                "/api/v1/warehouse",
            )
        )
        for method in route.methods or set()
    ]
    duplicates = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert duplicates == []
