from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import sqlalchemy as sa

VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spare_part_qty_numeric_migration_alters_column(monkeypatch: Any) -> None:
    migration = _load(
        "spare_qty_migration",
        "a7c3e9f1d2b4_spare_part_stock_qty_numeric.py",
    )
    assert migration.down_revision == "f2b4d8a6c1e9"
    calls: list[dict[str, Any]] = []

    def fake_alter_column(table: str, column: str, **kwargs: Any) -> None:
        calls.append({"table": table, "column": column, **kwargs})

    monkeypatch.setattr(migration.op, "alter_column", fake_alter_column)

    migration.upgrade()
    assert len(calls) == 1
    upgraded = calls[0]
    assert upgraded["table"] == "spare_part_stocks"
    assert upgraded["column"] == "current_qty"
    assert upgraded["schema"] == "equipment"
    assert isinstance(upgraded["type_"], sa.Numeric)
    assert upgraded["postgresql_using"] == "current_qty::numeric(12,2)"

    migration.downgrade()
    assert len(calls) == 2
    assert isinstance(calls[1]["type_"], sa.Integer)


def test_spare_part_unique_per_workshop_migration_swaps_index(
    monkeypatch: Any,
) -> None:
    migration = _load(
        "spare_unique_migration",
        "b8d4f2a6c9e1_spare_part_unique_per_workshop.py",
    )
    assert migration.down_revision == "a7c3e9f1d2b4"
    drops: list[tuple[str, Any]] = []
    creates: list[dict[str, Any]] = []

    def fake_drop_index(name: str, schema: Any = None) -> None:
        drops.append((name, schema))

    def fake_create_index(
        name: str, table: str, columns: list[str], **kwargs: Any
    ) -> None:
        creates.append(
            {"name": name, "table": table, "columns": tuple(columns), **kwargs}
        )

    monkeypatch.setattr(migration.op, "drop_index", fake_drop_index)
    monkeypatch.setattr(migration.op, "create_index", fake_create_index)

    migration.upgrade()
    assert drops == [("uq_spare_parts_code", "equipment")]
    assert len(creates) == 1
    created = creates[0]
    assert created["name"] == "uq_spare_parts_workshop_code"
    assert created["columns"] == ("workshop_code", "code")
    assert created["schema"] == "equipment"
    assert created["unique"] is True

    migration.downgrade()
    assert drops == [
        ("uq_spare_parts_code", "equipment"),
        ("uq_spare_parts_workshop_code", "equipment"),
    ]
    assert len(creates) == 2
    assert creates[1]["name"] == "uq_spare_parts_code"
    assert creates[1]["columns"] == ("code",)
