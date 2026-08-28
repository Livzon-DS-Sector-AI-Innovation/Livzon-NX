from app.platform.identity.rbac import (
    build_permission_catalog,
    match_action,
    match_module,
)


def test_migrated_rbac_catalog_keeps_module_and_subdomain_permissions() -> None:
    codes = {item["code"] for item in build_permission_catalog()}

    assert {"quality:read", "quality:write", "registration:read", "hr:write"} <= codes
    warehouse_write_codes = {
        "warehouse:product:write",
        "warehouse:hardware:write",
        "warehouse:raw:write",
    }
    assert warehouse_write_codes <= codes
    assert "module.view" not in codes


def test_rbac_path_mapping_covers_migrated_modules_and_admin_routes() -> None:
    assert match_module("/api/v1/quality/document-catalog/import") == "quality"
    assert match_module("/api/v1/registration/knowledge/articles") == "registration"
    assert match_module("/api/v1/hr/contracts") == "hr"
    assert match_module("/api/v1/warehouse/material-pages/raw") == "warehouse"
    assert match_module("/api/v1/identity/admin/roles") == "identity"
    assert match_action("GET") == "read"
    assert match_action("POST") == "write"
