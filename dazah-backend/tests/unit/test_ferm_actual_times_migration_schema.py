from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from sqlalchemy import Column

from alembic import op

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "d7e8f9a1b2c3_add_actual_times_to_fermentation_batch_actuals.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "ferm_actual_times_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ferm_actual_times_migration_extends_current_head() -> None:
    migration = _load_migration()
    assert migration.down_revision == "c9d400000057"
    assert migration.revision == "d7e8f9a1b2c3"


def test_ferm_actual_times_migration_adds_minute_columns(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    added: list[tuple[str, Column, str | None]] = []
    dropped: list[tuple[str, str | None]] = []

    def fake_add_column(
        table_name: str,
        column: Column,
        schema: str | None = None,
    ) -> None:
        added.append((table_name, column, schema))

    def fake_drop_column(
        table_name: str,
        column_name: str,
        schema: str | None = None,
    ) -> None:
        dropped.append((column_name, schema))

    monkeypatch.setattr(migration.op, "add_column", fake_add_column)
    monkeypatch.setattr(migration.op, "drop_column", fake_drop_column)

    migration.upgrade()

    assert [(t, c.name, s) for t, c, s in added] == [
        ("fermentation_batch_actuals", "inoculated_at", "production"),
        ("fermentation_batch_actuals", "dumped_at", "production"),
    ]
    for _, column, _ in added:
        assert column.nullable is True

    migration.downgrade()

    # 降级按添加的逆序删除两列
    assert dropped == [
        ("dumped_at", "production"),
        ("inoculated_at", "production"),
    ]
    # op 别名未被改动（防止 monkeypatch 泄漏到 alembic 全局 op）
    assert op is not None
