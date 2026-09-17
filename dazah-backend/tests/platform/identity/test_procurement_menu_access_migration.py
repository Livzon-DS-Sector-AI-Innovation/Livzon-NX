"""Check the procurement menu activation and retirement migration scope."""

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
    / "c9d400000046_activate_procurement_permission_pages.py"
)


def test_only_current_procurement_pages_are_activated_and_stale_menus_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "procurement_menu_access", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[Update] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()

    activation_count = len(migration._PROCUREMENT_PAGES_TO_ACTIVATE)
    assert len(statements) == activation_count + len(migration._STALE_PROCUREMENT_MENUS)

    activated = statements[:activation_count]
    actual_activated: set[tuple[str, str]] = set()
    for statement in activated:
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        actual_activated.add((params["key_1"], params["route_path_1"]))
        assert params["status_1"] == "disabled"
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["status"] == "active"
    assert actual_activated == set(migration._PROCUREMENT_PAGES_TO_ACTIVATE)

    retired = statements[activation_count:]
    actual_retired: set[tuple[str, str | None]] = set()
    for statement in retired:
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        route_path = params.get("route_path_1")
        actual_retired.add((params["key_1"], route_path))
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["status"] == "disabled"
        assert params["is_deleted"] is True
    assert actual_retired == set(migration._STALE_PROCUREMENT_MENUS)
