"""The legacy-scope migration must not activate invalid department grants."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa

from app.platform.identity.page_policy import GLOBAL_RESOURCE_PAGES, PAGE_DEFINITIONS


def test_unowned_or_mixed_pages_advertise_full_range_only() -> None:
    catalog = {page.page_key: page for page in PAGE_DEFINITIONS}
    for page_key in GLOBAL_RESOURCE_PAGES:
        assert catalog[page_key].supported_scope_types == ("all",)


def test_reviewed_department_pages_use_record_ownership_families() -> None:
    reviewed_modules = {
        "production", "registration", "quality", "hr", "warehouse", "procurement"
    }
    scoped = [
        page for page in PAGE_DEFINITIONS
        if page.module_code in reviewed_modules
        and "departments" in page.supported_scope_types
    ]
    assert len(scoped) == 95
    assert {
        module_code: sum(page.module_code == module_code for page in scoped)
        for module_code in reviewed_modules
    } == {
        "production": 0,
        "registration": 0,
        "quality": 7,
        "hr": 16,
        "warehouse": 16,
        "procurement": 56,
    }
    quality_pages = {
        page.page_key for page in scoped if page.module_code == "quality"
    }
    assert quality_pages == {
        "quality:documents",
        "quality:deviations:deviation-ledger",
        "quality:capas:capa-ledger",
        "quality:capas:capa-plans",
        "quality:change:change-ledger",
        "quality:change:file-change-ledger",
        "quality:change:change-action-plans",
    }
    assert all(
        page.page_key.startswith(("purchasing:request:", "purchasing:approval:"))
        or page.page_key == "purchasing:order"
        for page in scoped if page.module_code == "procurement"
    )
    assert all(
        page.page_key.startswith("warehouse:hardware:hardware-hardware-")
        for page in scoped if page.module_code == "warehouse"
    )


def test_only_previously_global_pages_are_converted() -> None:
    migration_path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/c9d400000048_page_data_scopes.py"
    )
    spec = spec_from_file_location("page_scope_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    metadata = sa.MetaData()
    grants = sa.Table(
        "grants", metadata,
        sa.Column("page_key", sa.String, primary_key=True),
    )
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(grants.insert(), [
            {"page_key": "production:overview"},
            {"page_key": "quality:product-quality:product-quality-mfn"},
            {"page_key": "hr:employee-management:profile"},
            {"page_key": "quality:deviations:deviation-ledger"},
            {"page_key": "equipment:assets"},
            *({"page_key": page_key} for page_key in GLOBAL_RESOURCE_PAGES),
        ])
        matching = set(connection.scalars(
            sa.select(grants.c.page_key).where(
                migration._legacy_global_page(grants.c.page_key)
            )
        ))
    assert matching == {
        "production:overview",
        "quality:product-quality:product-quality-mfn",
    }
    with engine.connect() as connection:
        global_resources = set(connection.scalars(
            sa.select(grants.c.page_key).where(
                migration._global_resource_page(grants.c.page_key)
            )
        ))
    assert global_resources == GLOBAL_RESOURCE_PAGES
