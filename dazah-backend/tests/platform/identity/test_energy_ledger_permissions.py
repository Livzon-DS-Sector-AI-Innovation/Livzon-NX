from app.platform.identity.page_lifecycle import lifecycle_catalog_errors, load_ledger
from app.platform.identity.page_policy import (
    PAGE_DEFINITIONS,
    api_binding_for_route,
    get_page_definition,
)


def test_historical_energy_pages_are_retired_and_cannot_be_granted() -> None:
    ledger = load_ledger()["pages"]
    for key in ("sources", "data", "sync-runs", "feishu-config"):
        page_key = f"energy:history:{key}"
        assert get_page_definition(page_key) is None
        assert ledger[page_key]["status"] == "retired"
        assert ledger[page_key]["route_path"] == f"/energy/{key}"
        assert all(
            action["status"] == "retired"
            for action in ledger[page_key]["actions"].values()
        )


def test_native_energy_has_reviewed_page_permissions_without_department_scopes() -> (
    None
):
    entry = api_binding_for_route("PUT", "/api/v1/energy/input-readings")
    assert entry is not None and entry.permission == "operate"
    assert entry.scope_adapter == "not_applicable"
    assert "energy:reports" not in entry.page_keys
    settings = api_binding_for_route("PUT", "/api/v1/energy/bot-config")
    assert settings is not None and settings.page_keys == ("energy:settings",)
    report = get_page_definition("energy:reports")
    assert report is not None and "not_applicable" in report.supported_scope_types
    assert "departments" not in report.supported_scope_types
    pages = [page for page in PAGE_DEFINITIONS if page.module_code == "energy"]
    ledger = {
        "pages": {
            key: value
            for key, value in load_ledger()["pages"].items()
            if key.startswith("energy:")
        }
    }
    assert not lifecycle_catalog_errors(pages, ledger)


def test_merged_ledger_keeps_entry_and_query_permissions_separate() -> None:
    entry = get_page_definition("energy:entry")
    report = get_page_definition("energy:reports")
    assert entry is not None and report is not None
    assert entry.page_name == "原始数据填写"
    assert report.page_name == "能源台账"
    assert entry.route_path == "/energy/entry"
    assert report.route_path == "/energy/reports"
    write = api_binding_for_route("PUT", "/api/v1/energy/input-readings")
    assert write is not None
    assert "energy:entry" in write.page_keys
    assert "energy:reports" not in write.page_keys
