from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "f7a2c9d4e6b1_expand_procurement_request_fields.py"
)
CATEGORY_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "a1c4e8f2b6d0_merge_advertising_printing_category.py"
)
URGENT_ITEM_CATEGORY_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "b3d7f1a9c2e4_add_urgent_item_category.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "procurement_request_fields_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_category_migration():
    spec = importlib.util.spec_from_file_location(
        "advertising_printing_category_migration",
        CATEGORY_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_urgent_item_category_migration():
    spec = importlib.util.spec_from_file_location(
        "urgent_item_category_migration",
        URGENT_ITEM_CATEGORY_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_procurement_migration_adds_fields_and_archives_old_labor(
    monkeypatch,
) -> None:
    migration = _load_migration()
    added_columns: list[tuple[str, str, object]] = []
    executed_sql: list[str] = []

    def capture_add_column(table_name, column, *, schema):
        added_columns.append((table_name, column.name, column))

    monkeypatch.setattr(migration.op, "add_column", capture_add_column)
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: executed_sql.append(str(statement)),
    )

    migration.upgrade()

    assert {(table, name) for table, name, _ in added_columns} == {
        ("purchase_requests", "attachment_note"),
        ("purchase_request_items", "material_code"),
        ("purchase_request_items", "material_description"),
        ("purchase_request_items", "rule_model"),
    }
    assert all(column.nullable is False for _, _, column in added_columns)
    assert all(column.server_default is not None for _, _, column in added_columns)
    assert len(executed_sql) == 3
    assert all("labor-protection" in statement for statement in executed_sql)
    assert "purchase_request_items" in executed_sql[0]
    assert "purchase_request_approvals" in executed_sql[1]
    assert "purchase_requests" in executed_sql[2]


def test_procurement_migration_downgrade_drops_only_added_columns(
    monkeypatch,
) -> None:
    migration = _load_migration()
    dropped_columns: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name, *, schema: dropped_columns.append(
            (table_name, column_name)
        ),
    )

    migration.downgrade()

    assert dropped_columns == [
        ("purchase_request_items", "rule_model"),
        ("purchase_request_items", "material_description"),
        ("purchase_request_items", "material_code"),
        ("purchase_requests", "attachment_note"),
    ]


def test_category_migration_merges_legacy_advertising_and_printing(
    monkeypatch,
) -> None:
    migration = _load_category_migration()
    executed_sql: list[str] = []
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: executed_sql.append(str(statement)),
    )

    migration.upgrade()

    assert len(executed_sql) == 1
    assert "advertising-printing" in executed_sql[0]
    assert "advertising" in executed_sql[0]
    assert "printing" in executed_sql[0]


def test_urgent_item_category_migration_adds_and_backfills_item_category(
    monkeypatch,
) -> None:
    migration = _load_urgent_item_category_migration()
    added_columns: list[tuple[str, str, object]] = []
    executed_sql: list[str] = []
    altered_columns: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table_name, column, *, schema: added_columns.append(
            (table_name, column.name, column)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: executed_sql.append(str(statement)),
    )
    def capture_alter_column(
        table_name,
        column_name,
        *,
        existing_type,
        nullable,
        schema,
    ):
        altered_columns.append((table_name, column_name, nullable))

    monkeypatch.setattr(migration.op, "alter_column", capture_alter_column)

    migration.upgrade()

    assert added_columns[0][:2] == ("purchase_request_items", "item_category")
    assert added_columns[0][2].server_default is not None
    assert "purchase_requests" in executed_sql[0]
    assert "requests.category" in executed_sql[0]
    assert altered_columns == [("purchase_request_items", "item_category", False)]


def test_urgent_item_category_migration_downgrade_drops_column(monkeypatch) -> None:
    migration = _load_urgent_item_category_migration()
    dropped_columns: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name, *, schema: dropped_columns.append(
            (table_name, column_name)
        ),
    )

    migration.downgrade()

    assert dropped_columns == [("purchase_request_items", "item_category")]
