import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "d4f6a8b0c2e1_add_material_code_field_type.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "procurement_material_field_type_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_material_field_type_migration_upgrade_and_downgrade(monkeypatch: Any) -> None:
    migration = _load_migration()
    added: list[tuple[str, str, bool, str]] = []
    altered: list[tuple[str, str, str | None, str | None, str]] = []
    dropped: list[tuple[str, str, str]] = []

    def capture_add_column(table_name: Any, column: Any, schema: Any) -> Any:
        added.append((table_name, column.name, column.nullable, schema))

    monkeypatch.setattr(migration.op, "add_column", capture_add_column)
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda table_name, column_name, **kwargs: altered.append(
            (
                table_name,
                column_name,
                kwargs.get("comment"),
                kwargs.get("existing_comment"),
                kwargs["schema"],
            )
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name, schema: dropped.append(
            (table_name, column_name, schema)
        ),
    )

    migration.upgrade()
    migration.downgrade()

    assert added == [
        (
            "material_source_configs",
            "material_code_field_type",
            True,
            "procurement",
        )
    ]
    assert altered == [
        (
            "purchase_request_items",
            "rule_model",
            "规格型号",
            "规则型号",
            "procurement",
        ),
        (
            "purchase_request_items",
            "rule_model",
            "规则型号",
            "规格型号",
            "procurement",
        ),
    ]
    assert dropped == [
        (
            "material_source_configs",
            "material_code_field_type",
            "procurement",
        )
    ]
