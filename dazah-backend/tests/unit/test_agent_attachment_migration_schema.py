from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c6d4e8f2a913_add_agent_persistent_attachments.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "agent_attachment_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_attachment_migration_extends_current_head() -> None:
    migration = _load_migration()

    assert migration.revision == "c6d4e8f2a913"
    assert migration.down_revision == "8b42d1e6f903"


def test_agent_attachment_migration_creates_expected_table_and_indexes(
    monkeypatch: Any,
) -> None:
    migration = _load_migration()
    created_tables: dict[str, tuple[tuple[object, ...], dict[str, object]]] = {}
    created_indexes: list[tuple[str, str, tuple[str, ...], str | None]] = []

    def capture_create_table(
        name: str,
        *items: object,
        **kwargs: object,
    ) -> None:
        created_tables[name] = (items, kwargs)

    def capture_create_index(
        name: str,
        table_name: str,
        columns: list[str],
        *,
        schema: str | None = None,
    ) -> None:
        created_indexes.append((name, table_name, tuple(columns), schema))

    monkeypatch.setattr(migration.op, "create_table", capture_create_table)
    monkeypatch.setattr(migration.op, "create_index", capture_create_index)

    migration.upgrade()

    table_items, table_kwargs = created_tables["agent_attachments"]
    column_names = {item.name for item in table_items if hasattr(item, "type")}  # type: ignore[attr-defined]

    assert table_kwargs["schema"] == "core"
    assert {
        "id",
        "session_id",
        "message_id",
        "user_id",
        "filename",
        "content_type",
        "size",
        "kind",
        "object_key",
        "sha256",
        "extracted_text",
        "version",
        "is_deleted",
    } <= column_names
    assert {name for name, _, _, _ in created_indexes} == {
        "ix_core_agent_attachments_session_active",
        "ix_core_agent_attachments_session_id",
        "ix_core_agent_attachments_message_id",
        "ix_core_agent_attachments_user_id",
        "ix_core_agent_attachments_sha256",
    }
    assert all(
        table_name == "agent_attachments" and schema == "core"
        for _, table_name, _, schema in created_indexes
    )
