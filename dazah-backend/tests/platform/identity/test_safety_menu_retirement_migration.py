"""Keep the EHS menu cleanup limited to the retired application entry."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update


def test_only_the_active_legacy_ehs_application_menu_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/b2e9e5fc78d1_retire_legacy_safety_ehs_application_menu.py"
    )
    spec = importlib.util.spec_from_file_location("safety_menu_retirement", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[Update] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert len(statements) == 1
    compiled = statements[0].compile(dialect=postgresql.dialect())
    assert str(compiled).startswith("UPDATE identity.menus ")
    assert "identity.menus.is_deleted IS false" in str(compiled)
    assert compiled.params == {
        "status": "disabled",
        "key_1": "safety:risk-hazard:ehs-change:ehs-change-apply",
        "route_path_1": "/safety/ehs-change",
        "type_1": "menu",
        "status_1": "active",
    }

    migration.downgrade()
    assert len(statements) == 1
