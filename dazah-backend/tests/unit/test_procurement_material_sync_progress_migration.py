import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "f5e4d3c2b1a0_add_material_sync_progress.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "material_sync_progress_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_material_sync_progress_migration_adds_progress_columns(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    added_columns: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table_name, column, *, schema: added_columns.append(
            (table_name, column.name, column.nullable)
        ),
    )

    migration.upgrade()

    assert added_columns == [
        ("material_source_configs", "sync_total_records", True),
        ("material_source_configs", "sync_fetched_count", True),
    ]


def test_material_sync_progress_migration_downgrade_drops_columns(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    dropped_columns: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name, **_kwargs: dropped_columns.append(
            (table_name, column_name)
        ),
    )

    migration.downgrade()

    assert dropped_columns == [
        ("material_source_configs", "sync_fetched_count"),
        ("material_source_configs", "sync_total_records"),
    ]
