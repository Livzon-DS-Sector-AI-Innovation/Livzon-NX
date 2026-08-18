import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "e6a7b8c9d0e1_add_procurement_material_catalog.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "procurement_material_catalog_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_material_catalog_migration_creates_mirror_and_sync_metadata(
    monkeypatch,
) -> None:
    migration = _load_migration()
    added_columns: list[tuple[str, str, bool]] = []
    created_tables: list[tuple[str, dict[str, object]]] = []
    created_indexes: list[tuple[str, str, list[str]]] = []

    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table_name, column, *, schema: added_columns.append(
            (table_name, column.name, column.nullable)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda table_name, *columns, **kwargs: created_tables.append(
            (table_name, kwargs)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda index_name, table_name, columns, **_kwargs: created_indexes.append(
            (index_name, table_name, columns)
        ),
    )

    migration.upgrade()

    assert added_columns == [
        ("material_source_configs", "sync_status", False),
        ("material_source_configs", "sync_error", True),
        ("material_source_configs", "last_synced_at", True),
        ("material_source_configs", "last_sync_record_count", False),
    ]
    assert created_tables == [("material_catalog_records", {"schema": "procurement"})]
    assert {item[0] for item in created_indexes} == {
        "ix_procurement_material_catalog_source_active",
        "ix_procurement_material_catalog_code",
        "ix_procurement_material_catalog_description",
        "ix_procurement_material_catalog_rule_model",
    }


def test_material_catalog_migration_downgrade_removes_all_objects(monkeypatch) -> None:
    migration = _load_migration()
    dropped_indexes: list[str] = []
    dropped_tables: list[str] = []
    dropped_columns: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda index_name, **_kwargs: dropped_indexes.append(index_name),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table_name, **_kwargs: dropped_tables.append(table_name),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name, **_kwargs: dropped_columns.append(
            (table_name, column_name)
        ),
    )

    migration.downgrade()

    assert len(dropped_indexes) == 4
    assert dropped_tables == ["material_catalog_records"]
    assert dropped_columns == [
        ("material_source_configs", "last_sync_record_count"),
        ("material_source_configs", "last_synced_at"),
        ("material_source_configs", "sync_error"),
        ("material_source_configs", "sync_status"),
    ]
