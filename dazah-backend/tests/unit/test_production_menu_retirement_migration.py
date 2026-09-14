from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c9d400000034_retire_legacy_production_cost_menu.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "retire_legacy_production_cost_menu_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_upgrade_aligns_legacy_production_menu_rows(
    monkeypatch,
) -> None:
    migration = _load_migration()
    statements: list[sa.sql.Update] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 3

    directory_statements = statements[:2]
    for statement in directory_statements:
        rendered = str(statement)
        assert "type" in rendered
        assert "route_path" in rendered
        assert "is_deleted" in rendered
        params = statement.compile().params
        assert (
            "/production/batches" in params.values()
            or "/production/plan" in params.values()
        )
        assert "directory" in params.values()

    cost_statement = statements[2]
    rendered = str(cost_statement)
    assert "status" in rendered
    assert "is_deleted" in rendered
    params = cost_statement.compile().params
    assert "production:cost" in params.values()
    assert "/production/cost" in params.values()
    assert "disabled" in params.values()
