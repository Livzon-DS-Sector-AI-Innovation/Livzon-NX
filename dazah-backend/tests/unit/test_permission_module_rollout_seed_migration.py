from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c9d400000033_seed_review_pending_permission_rollouts.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "review_pending_permission_rollout_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_reviewed_modules_are_seeded_as_draft_without_overwriting_rollouts(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    statements: list[Any] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 4
    assert {item._bindparams["module_code"].value for item in statements} == {
        "hr",
        "warehouse",
        "registration",
        "production",
    }
    for statement in statements:
        assert "ON CONFLICT (module_code) DO NOTHING" in str(statement)
        assert "'draft'" in str(statement)
        assert isinstance(statement._bindparams["id"].type, sa.Uuid)
        assert isinstance(statement._bindparams["id"].value, UUID)
