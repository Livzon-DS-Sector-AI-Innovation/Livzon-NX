from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import Boolean

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "4e7b9c1d2f30_add_agent_v2_identity_and_tool_catalog.py"
)
ALIGNMENT_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "9a1c2e3f4b5d_align_agent_v2_identity_metadata.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("agent_v2_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_alignment_migration():
    spec = importlib.util.spec_from_file_location(
        "agent_v2_alignment_migration",
        ALIGNMENT_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_v2_migration_is_current_linear_head() -> None:
    migration = _load_migration()

    assert migration.revision == "4e7b9c1d2f30"
    assert migration.down_revision == "fbffa92623e9"


def test_admin_enabled_belongs_to_tool_catalog_only(
    monkeypatch,
) -> None:
    migration = _load_migration()
    created_tables: dict[str, list[object]] = {}

    def capture_create_table(name: str, *items: object, **_: object) -> None:
        created_tables[name] = list(items)

    monkeypatch.setattr(migration.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "drop_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "drop_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "create_table", capture_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(migration.op, "execute", lambda *args, **kwargs: None)

    migration.upgrade()

    binding_names = {
        item.name
        for item in created_tables["external_identity_bindings"]
        if hasattr(item, "name")
    }
    catalog_columns = {
        item.name: item
        for item in created_tables["agent_tool_catalog"]
        if hasattr(item, "type")
    }

    assert "admin_enabled" not in binding_names
    assert isinstance(catalog_columns["admin_enabled"].type, Boolean)
    assert catalog_columns["admin_enabled"].nullable is False


def test_alignment_migration_adds_model_index_and_column_comments(
    monkeypatch,
) -> None:
    migration = _load_alignment_migration()
    created_indexes: list[tuple[tuple[object, ...], dict[str, object]]] = []
    altered_columns: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda *args, **kwargs: created_indexes.append((args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda *args, **kwargs: altered_columns.append((args, kwargs)),
    )

    migration.upgrade()

    assert migration.revision == "9a1c2e3f4b5d"
    assert migration.down_revision == "4e7b9c1d2f30"
    assert created_indexes == [
        (
            (
                "ix_identity_external_identity_bindings_local_user_id",
                "external_identity_bindings",
                ["local_user_id"],
            ),
            {"unique": False, "schema": "identity"},
        )
    ]
    assert {
        (args[0], args[1]): kwargs["comment"]
        for args, kwargs in altered_columns
    } == {
        ("feishu_configs", "tenant_id"): "Gateway 可信租户标识",
        ("feishu_configs", "gateway_enabled"): "是否启用 Hermes Feishu Gateway",
        ("feishu_configs", "config_version"): "Gateway 配置单调递增版本",
    }


def test_alignment_migration_downgrade_removes_metadata(
    monkeypatch,
) -> None:
    migration = _load_alignment_migration()
    altered_columns: list[tuple[tuple[object, ...], dict[str, object]]] = []
    dropped_indexes: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda *args, **kwargs: altered_columns.append((args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda *args, **kwargs: dropped_indexes.append((args, kwargs)),
    )

    migration.downgrade()

    assert len(altered_columns) == 3
    assert all(kwargs["comment"] is None for _, kwargs in altered_columns)
    assert dropped_indexes == [
        (
            ("ix_identity_external_identity_bindings_local_user_id",),
            {
                "table_name": "external_identity_bindings",
                "schema": "identity",
            },
        )
    ]
