"""Keep the production menu activation migration scoped to the three stale rows."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "c9d400000043_activate_production_permission_pages.py"
)


def test_only_stale_production_pages_are_activated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "production_menu_activation", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[Update] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()

    assert len(statements) == 3
    expected = {
        ("production:process", "/production/process"),
        ("production:records", "/production/records"),
        ("production:balance", "/production/balance"),
    }
    actual: set[tuple[str, str]] = set()
    for statement in statements:
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        actual.add((params["key_1"], params["route_path_1"]))
        assert params["status_1"] == "disabled"
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["status"] == "active"

    assert actual == expected
