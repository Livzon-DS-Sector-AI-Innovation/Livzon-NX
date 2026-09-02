from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "d2f8a4c6e1b3_add_page_permission_matrix.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "page_permission_migration", MIGRATION_PATH
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_module_rollout_seed_binds_uuid_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    statements: list[Any] = []

    monkeypatch.setattr(migration.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: statements.append(statement),
    )

    migration.upgrade()

    assert len(statements) == 4
    assert all(
        isinstance(statement._bindparams["id"].type, sa.Uuid)
        for statement in statements
    )
