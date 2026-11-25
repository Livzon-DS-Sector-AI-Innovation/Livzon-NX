"""Schema assertions for the material price migration."""

import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c3f7a1d9e2b4_add_material_price_records.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "material_price_records_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_material_price_migration_creates_table_columns_and_indexes(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    created_tables: list[tuple[str, list[str], dict[str, object]]] = []
    created_indexes: list[tuple[str, str, list[str], bool]] = []
    executed: list[str] = []

    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: executed.append(statement),
    )
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda table_name, *columns, **kwargs: created_tables.append(
            (table_name, [column.name for column in columns], kwargs)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda index_name, table_name, columns, *, unique, **_kwargs: (
            created_indexes.append((index_name, table_name, columns, unique))
        ),
    )

    migration.upgrade()

    assert executed == ["CREATE SCHEMA IF NOT EXISTS procurement"]
    assert len(created_tables) == 1
    table_name, column_names, kwargs = created_tables[0]
    assert table_name == "material_price_records"
    assert kwargs["schema"] == "procurement"
    for required in (
        "data_year",
        "data_date",
        "doc_no",
        "department",
        "sub_inventory",
        "batch_no",
        "material_code",
        "material_name",
        "material_alias",
        "unit",
        "material_category",
        "cost_category",
        "unit_price",
        "quantity",
        "amount",
        "supplier_name",
        "price_flag",
        "source_type",
        "row_key",
        "source_file",
        "source_sheet",
        "source_row",
        "raw_data",
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "is_deleted",
    ):
        assert required in column_names, required

    unique_indexes = [item for item in created_indexes if item[3]]
    assert unique_indexes == [
        (
            "uq_procurement_price_row_key",
            "material_price_records",
            ["row_key"],
            True,
        )
    ]
    indexed_columns = {
        column for _, _, columns, _ in created_indexes for column in columns
    }
    assert {
        "material_code",
        "material_name",
        "data_year",
        "cost_category",
    } <= indexed_columns


def test_material_price_migration_downgrade_drops_table(monkeypatch: Any) -> None:
    migration = _load_migration()
    dropped_indexes: list[str] = []
    dropped_tables: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda index_name, **_kwargs: dropped_indexes.append(index_name),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table_name, *, schema: dropped_tables.append((table_name, schema)),
    )

    migration.downgrade()

    assert dropped_tables == [("material_price_records", "procurement")]
    assert "uq_procurement_price_row_key" in dropped_indexes
