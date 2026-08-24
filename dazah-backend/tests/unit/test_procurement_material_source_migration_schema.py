import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c8e4f1a2b3d5_add_procurement_material_source_config.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "procurement_material_source_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_material_source_migration_creates_expected_table(monkeypatch: Any) -> None:
    migration = _load_migration()
    created: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    indexes: list[tuple[str, str, list[str], bool, str]] = []

    def capture_create_table(table_name: Any, *columns: Any, **kwargs: Any) -> Any:
        created.append((table_name, columns, kwargs))

    monkeypatch.setattr(migration.op, "create_table", capture_create_table)
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, unique, schema: indexes.append(
            (name, table, columns, unique, schema)
        ),
    )

    migration.upgrade()

    assert len(created) == 1
    table_name, columns, kwargs = created[0]
    assert table_name == "material_source_configs"
    assert kwargs == {"schema": "procurement"}
    column_names = {column.name for column in columns if hasattr(column, "name")}
    assert {
        "id",
        "source_url",
        "app_token",
        "table_id",
        "view_id",
        "material_code_field",
        "material_description_field",
        "rule_model_field",
        "last_test_status",
        "last_test_error",
        "last_tested_at",
    } <= column_names
    assert indexes == [
        (
            "ix_procurement_material_source_config_active",
            "material_source_configs",
            ["config_key", "is_deleted"],
            False,
            "procurement",
        )
    ]


def test_material_source_migration_downgrade_drops_index_and_table(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    dropped_indexes: list[tuple[str, str, str]] = []
    dropped_tables: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name, schema: dropped_indexes.append(
            (name, table_name, schema)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table_name, schema: dropped_tables.append((table_name, schema)),
    )

    migration.downgrade()

    assert dropped_indexes == [
        (
            "ix_procurement_material_source_config_active",
            "material_source_configs",
            "procurement",
        )
    ]
    assert dropped_tables == [("material_source_configs", "procurement")]
