"""Check the retired production menu migration cannot touch other routes."""

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
    / "c9d400000044_retire_production_menu_pages.py"
)


def test_only_removed_production_menus_are_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "production_menu_retirement", MIGRATION_PATH
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
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["status"] == "disabled"
        assert params["is_deleted"] is True

    assert actual == expected
