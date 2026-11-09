"""Dashboard naming keeps the existing page permission identity."""

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.page_policy import get_page_definition


def test_energy_dashboard_menu_and_permission_catalog_agree() -> None:
    energy = next(menu for menu in SEED_MENUS if menu["key"] == "energy")
    overview = next(item for item in energy["children"] if item["path"] == "/energy")
    assert overview["name"] == "能源仪表盘"
    page = get_page_definition("energy:ledger-overview")
    assert page is not None
    assert page.page_name == "能源仪表盘"
    assert page.route_path == "/energy"


def test_energy_reports_name_preserves_query_and_entry_permission_keys() -> None:
    energy = next(menu for menu in SEED_MENUS if menu["key"] == "energy")
    reports = next(
        item for item in energy["children"] if item["path"] == "/energy/reports"
    )
    assert reports["name"] == "能源报表"
    page = get_page_definition("energy:reports")
    assert page is not None
    assert page.page_name == "能源报表"
    assert page.route_path == "/energy/reports"
    entry = get_page_definition("energy:entry")
    assert entry is not None
    assert entry.route_path == "/energy/entry"
