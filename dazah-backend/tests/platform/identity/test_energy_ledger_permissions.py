from app.platform.identity.page_lifecycle import lifecycle_catalog_errors, load_ledger
from app.platform.identity.page_policy import (
    PAGE_DEFINITIONS,
    api_binding_for_route,
    get_page_definition,
)


def test_native_energy_has_reviewed_page_permissions_and_department_scopes() -> None:
    entry = api_binding_for_route("POST", "/api/v1/energy/entry-tasks/{task_id}/submit")
    assert entry is not None and entry.permission == "operate"
    assert entry.scope_adapter == "energy.owner"
    assert "energy:reports" not in entry.page_keys
    settings = api_binding_for_route("PUT", "/api/v1/energy/period-locks/{month}")
    assert settings is not None and settings.page_keys == ("energy:settings",)
    report = get_page_definition("energy:reports")
    assert report is not None and "departments" in report.supported_scope_types
    assert "not_applicable" not in report.supported_scope_types
    pages = [page for page in PAGE_DEFINITIONS if page.module_code == "energy"]
    ledger = {
        "pages": {
            key: value
            for key, value in load_ledger()["pages"].items()
            if key.startswith("energy:")
        }
    }
    assert not lifecycle_catalog_errors(pages, ledger)
