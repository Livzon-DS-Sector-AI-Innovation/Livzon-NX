"""Check the quality menu cleanup migration has an exact, bounded scope."""

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
    / "c9d400000045_retire_quality_menu_pages.py"
)


def test_only_stale_quality_menus_are_retired_and_current_leaves_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "quality_menu_retirement", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[Update] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()

    retired_count = len(migration._RETIRED_QUALITY_MENUS)
    leaf_count = len(migration._INSPECTION_LEAF_MENUS)
    assert len(statements) == retired_count + leaf_count

    retired = statements[:retired_count]
    actual_retired: set[tuple[str, str]] = set()
    for statement in retired:
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        actual_retired.add((params["key_1"], params["route_path_1"]))
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["status"] == "disabled"
        assert params["is_deleted"] is True

    assert actual_retired == set(migration._RETIRED_QUALITY_MENUS)

    normalized = statements[retired_count:]
    actual_leaves: set[tuple[str, str]] = set()
    for statement in normalized:
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        actual_leaves.add((params["key_1"], params["route_path_1"]))
        assert params["type_1"] == "directory"
        assert params["status_1"] == "active"
        assert "identity.menus.is_deleted IS false" in str(compiled)
        assert params["type"] == "menu"

    assert actual_leaves == set(migration._INSPECTION_LEAF_MENUS)
