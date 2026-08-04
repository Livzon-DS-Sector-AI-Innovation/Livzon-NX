from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import Boolean

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "4e7b9c1d2f30_add_agent_v2_identity_and_tool_catalog.py"
)
GOVERNANCE_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "7a31c9e4d2b8_add_agent_governance_controls.py"
)
ALIGNMENT_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "9a1c2e3f4b5d_align_agent_v2_identity_metadata.py"
)


def _load_migration(path: Path = MIGRATION_PATH):
    spec = importlib.util.spec_from_file_location("agent_v2_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_governance_migration_extends_v2_head() -> None:
    migration = _load_migration()
    alignment = _load_migration(ALIGNMENT_MIGRATION_PATH)
    governance = _load_migration(GOVERNANCE_MIGRATION_PATH)

    assert migration.revision == "4e7b9c1d2f30"
    assert migration.down_revision == "fbffa92623e9"
    assert alignment.revision == "9a1c2e3f4b5d"
    assert alignment.down_revision == migration.revision
    assert governance.revision == "7a31c9e4d2b8"
    assert governance.down_revision == alignment.revision


def test_admin_enabled_belongs_to_tool_catalog_only(
    monkeypatch,
) -> None:
    migration = _load_migration()
    created_tables: dict[str, list[object]] = {}

    def capture_create_table(name: str, *items: object, **_: object) -> None:
        created_tables[name] = list(items)

    monkeypatch.setattr(migration.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "drop_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "drop_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_table", capture_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "execute", lambda *args, **kwargs: None)

    migration.upgrade()

    binding_names = {
        item.name
        for item in created_tables["external_identity_bindings"]
        if hasattr(item, "name")
    }
    catalog_columns = {
        item.name: item
        for item in created_tables["agent_tool_catalog"]
        if hasattr(item, "type")
    }

    assert "admin_enabled" not in binding_names
    assert isinstance(catalog_columns["admin_enabled"].type, Boolean)
    assert catalog_columns["admin_enabled"].nullable is False
