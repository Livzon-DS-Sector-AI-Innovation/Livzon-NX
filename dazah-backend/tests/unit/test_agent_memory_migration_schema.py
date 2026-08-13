from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "d3b7a9c1e5f2_add_agent_memory_governance.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "agent_memory_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_memory_migration_extends_current_head() -> None:
    migration = _load_migration()
    assert migration.down_revision == "c6d4e8f2a913"


def test_agent_memory_migration_creates_governance_tables(monkeypatch) -> None:
    migration = _load_migration()
    tables: list[str] = []
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda name, *items, **kwargs: tables.append(name),
    )
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)

    migration.upgrade()

    assert tables == [
        "agent_memory_tenant_policies",
        "agent_memory_user_preferences",
        "agent_memory_clear_confirmations",
    ]
