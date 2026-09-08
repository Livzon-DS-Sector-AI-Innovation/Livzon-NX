from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "f8e7d6c5b4a3_add_batch_lineage_unique_constraint.py"
)
CONSTRAINT_NAME = "uq_batch_lineage_link"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "batch_lineage_unique_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_batch_lineage_unique_migration_extends_current_head() -> None:
    migration = _load_migration()
    assert migration.down_revision == "c9d400000022"


def test_batch_lineage_unique_migration_creates_constraint(monkeypatch: Any) -> None:
    migration = _load_migration()
    calls: list[tuple[Any, ...]] = []

    def fake_create_unique_constraint(
        constraint_name: str,
        table_name: str,
        columns: list[str],
        schema: str | None = None,
    ) -> None:
        calls.append((constraint_name, table_name, tuple(columns), schema))

    monkeypatch.setattr(
        migration.op,
        "create_unique_constraint",
        fake_create_unique_constraint,
    )

    migration.upgrade()

    assert calls == [
        (
            CONSTRAINT_NAME,
            "batch_lineage",
            (
                "upstream_type",
                "upstream_batch",
                "downstream_type",
                "downstream_batch",
            ),
            "production",
        )
    ]


def test_batch_lineage_unique_migration_downgrade_drops_constraint(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    calls: list[tuple[Any, ...]] = []

    def fake_drop_constraint(
        constraint_name: str,
        table_name: str,
        schema: str | None = None,
    ) -> None:
        calls.append((constraint_name, table_name, schema))

    monkeypatch.setattr(migration.op, "drop_constraint", fake_drop_constraint)

    migration.downgrade()

    assert calls == [(CONSTRAINT_NAME, "batch_lineage", "production")]
