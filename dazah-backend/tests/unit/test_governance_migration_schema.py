"""Check the workshop and sensitive-action migrations after the merged main head."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa


def _load_migration(filename: str) -> ModuleType:
    path = Path(__file__).parents[2] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workshop_ownership_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration("c9d400000041_batch_workshop_ownership.py")
    assert migration.revision == "c9d400000041"
    assert migration.down_revision == "c9d400000040"
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        migration.op, "add_column", lambda *a, **kw: calls.append(("add", a, kw))
    )
    monkeypatch.setattr(
        migration.op, "create_index", lambda *a, **kw: calls.append(("index", a, kw))
    )
    monkeypatch.setattr(
        migration.op, "drop_index", lambda *a, **kw: calls.append(("drop_index", a, kw))
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda *a, **kw: calls.append(("drop_column", a, kw)),
    )

    migration.upgrade()
    assert [name for name, _, _ in calls] == ["add", "index"]
    assert calls[0][1][0] == "batches"
    column = calls[0][1][1]
    assert isinstance(column, sa.Column)
    assert column.name == "workshop_code" and column.nullable is True
    assert calls[0][2]["schema"] == "production"
    migration.downgrade()
    assert [name for name, _, _ in calls[-2:]] == ["drop_index", "drop_column"]


def test_sensitive_action_expiry_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration("c9d400000042_page_permission_risk_expiry.py")
    assert migration.revision == "c9d400000042"
    assert migration.down_revision == "c9d400000041"
    added: list[tuple[str, sa.Column[object], str]] = []
    dropped: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table, column, *, schema: added.append((table, column, schema)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table, column, *, schema: dropped.append((table, column, schema)),
    )

    migration.upgrade()
    assert [table for table, _, _ in added] == ["role_page_grants", "user_page_grants"]
    assert all(column.name == "sensitive_actions_expires_at" for _, column, _ in added)
    assert all(
        column.nullable is True and schema == "identity" for _, column, schema in added
    )
    migration.downgrade()
    assert dropped == [
        ("user_page_grants", "sensitive_actions_expires_at", "identity"),
        ("role_page_grants", "sensitive_actions_expires_at", "identity"),
    ]
