from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

BACKEND_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "d2f8a4c6e1b3_add_page_permission_matrix.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "page_permission_matrix_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_rollout_seed_ids_are_bound_as_uuid(monkeypatch: Any) -> None:
    migration = _load_migration()
    executed: list[Any] = []

    monkeypatch.setattr(migration.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.upgrade()

    assert len(executed) == 4
    for statement in executed:
        id_param = statement._bindparams["id"]
        assert isinstance(id_param.type, sa.Uuid)
        assert isinstance(id_param.value, UUID)
