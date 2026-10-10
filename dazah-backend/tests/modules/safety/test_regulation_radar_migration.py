"""法规雷达迁移链断言（3 个迁移的表/列 DDL 与回退）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

_VERSIONS = Path(__file__).resolve().parents[3] / "alembic/versions"
_CHAIN = [
    "a7c3e5b9d1f2_create_regulation_radar_tables",
    "c5d7f9a3e8b2_add_radar_notify_settings",
    "d9e1f2a4b6c8_add_radar_scan_enabled",
]
_RADAR_COLUMNS = {
    "source_type",
    "standard_no",
    "version_status",
    "version_checked_at",
    "ai_analysis",
}
_NOTIFY_COLUMNS = {
    "radar_notify_enabled",
    "radar_notify_chat_ids",
    "radar_notify_user_ids",
}


def _load(name: str):
    path = _VERSIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chain_is_linear_after_knowledge_head() -> None:
    """雷达三个迁移必须自 f8d4b6e2c9a1 起单线串联，无分叉。"""
    modules = {name: _load(name) for name in _CHAIN}
    assert modules["a7c3e5b9d1f2_create_regulation_radar_tables"].down_revision == (
        "f8d4b6e2c9a1"
    )
    assert modules["c5d7f9a3e8b2_add_radar_notify_settings"].down_revision == (
        "a7c3e5b9d1f2"
    )
    assert modules["d9e1f2a4b6c8_add_radar_scan_enabled"].down_revision == (
        "c5d7f9a3e8b2"
    )
    by_rev = {module.revision: module for module in modules.values()}
    children = [
        module.revision
        for module in modules.values()
        if module.down_revision in by_rev
    ]
    assert sorted(children) == ["c5d7f9a3e8b2", "d9e1f2a4b6c8"], (
        f"链在中间分叉: {children}"
    )


def test_radar_tables_migration_adds_columns_and_tables(monkeypatch) -> None:
    module = _load("a7c3e5b9d1f2_create_regulation_radar_tables")
    add_column, create_table, create_index = Mock(), Mock(), Mock()
    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)

    module.upgrade()

    added_tables = {call.args[0] for call in add_column.call_args_list}
    assert added_tables == {"knowledge_articles"}
    column_names = set()
    for call in add_column.call_args_list:
        for value in call.args[1:]:
            if hasattr(value, "name"):
                column_names.add(value.name)
    assert column_names == _RADAR_COLUMNS
    assert all(
        call.kwargs.get("schema") == "safety" for call in add_column.call_args_list
    )

    created = {call.args[0] for call in create_table.call_args_list}
    assert created == {"regulation_radar_sites", "regulation_radar_runs"}
    assert all(
        call.kwargs.get("schema") == "safety" for call in create_table.call_args_list
    )
    assert create_index.called


def test_radar_tables_migration_drops_tables_on_downgrade(monkeypatch) -> None:
    module = _load("a7c3e5b9d1f2_create_regulation_radar_tables")
    drop_table, drop_column, drop_index = Mock(), Mock(), Mock()
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    monkeypatch.setattr(module.op, "drop_column", drop_column)
    monkeypatch.setattr(module.op, "drop_index", drop_index)

    module.downgrade()

    dropped = {call.args[0] for call in drop_table.call_args_list}
    assert dropped == {"regulation_radar_sites", "regulation_radar_runs"}
    dropped_columns = {call.args[1] for call in drop_column.call_args_list}
    assert dropped_columns == _RADAR_COLUMNS
    assert drop_index.called


def test_radar_notify_settings_migration_round_trip(monkeypatch) -> None:
    module = _load("c5d7f9a3e8b2_add_radar_notify_settings")
    add_column, drop_column = Mock(), Mock()
    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "drop_column", drop_column)

    module.upgrade()
    column_names = {
        value.name
        for call in add_column.call_args_list
        for value in call.args[1:]
        if hasattr(value, "name")
    }
    assert column_names == _NOTIFY_COLUMNS
    assert {call.args[0] for call in add_column.call_args_list} == {
        "feishu_app_settings"
    }
    assert all(
        call.kwargs.get("schema") == "safety" for call in add_column.call_args_list
    )

    module.downgrade()
    assert {call.args[1] for call in drop_column.call_args_list} == _NOTIFY_COLUMNS
    assert {call.args[0] for call in drop_column.call_args_list} == {
        "feishu_app_settings"
    }

def test_radar_scan_enabled_migration_round_trip(monkeypatch) -> None:
    module = _load("d9e1f2a4b6c8_add_radar_scan_enabled")
    add_column, drop_column = Mock(), Mock()
    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "drop_column", drop_column)

    module.upgrade()
    assert add_column.call_args.args[0] == "feishu_app_settings"
    column = next(arg for arg in add_column.call_args.args[1:] if hasattr(arg, "name"))
    assert column.name == "radar_scan_enabled"
    assert column.nullable is False
    assert str(column.server_default.arg) == "true"
    assert add_column.call_args.kwargs.get("schema") == "safety"

    module.downgrade()
    drop_column.assert_called_once_with(
        "feishu_app_settings", "radar_scan_enabled", schema="safety"
    )

