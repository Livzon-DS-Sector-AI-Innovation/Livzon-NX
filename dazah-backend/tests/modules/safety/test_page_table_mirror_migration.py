"""页面镜像迁移断言（镜像表 DDL、配置表加列与回退）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

_VERSIONS = Path(__file__).resolve().parents[3] / "alembic/versions"
_NAME = "a3c8e5f7b9d1_create_safety_page_table_mirror"

_MIRROR_COLUMNS = {
    "page_key",
    "record_id",
    "fields",
    "search_text",
    "synced_at",
    "created_at",
    "updated_at",
    "is_deleted",
}

_CONFIG_ADDED = {
    "is_mirrored",
    "last_synced_at",
    "last_sync_status",
    "last_sync_error",
    "last_sync_record_count",
}


def _load():
    path = _VERSIONS / f"{_NAME}.py"
    spec = importlib.util.spec_from_file_location(_NAME, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_from_safety_head() -> None:
    module = _load()
    assert module.revision == "a3c8e5f7b9d1"
    # 接在安全模块链头（workshop_classifications 之后），保持单链
    # 主线在 807ad84a1158 后又并行合入 c4e6f8a0b2d1（equipment ledger
    # archives）；本批改接其后续主线头保持单链
    assert module.down_revision == "c4e6f8a0b2d1"


def test_upgrade_creates_mirror_table_and_config_columns(monkeypatch) -> None:
    module = _load()
    create_table, create_index, add_column = Mock(), Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(module.op, "add_column", add_column)

    module.upgrade()

    assert create_table.call_args.args[0] == "page_table_mirror_records"
    assert create_table.call_args.kwargs["schema"] == "safety"
    column_names = {
        arg.name for arg in create_table.call_args.args[1:] if hasattr(arg, "name")
    }
    assert _MIRROR_COLUMNS.issubset(column_names)
    # (page_key, record_id) 部分唯一索引：软删后可重建同记录
    unique_calls = [c for c in create_index.call_args_list if c.kwargs.get("unique")]
    assert unique_calls, "缺少镜像表唯一索引"
    assert unique_calls[0].args[:3] == (
        "uq_safety_page_table_mirror_records_page_record",
        "page_table_mirror_records",
        ["page_key", "record_id"],
    )
    assert unique_calls[0].kwargs["postgresql_where"] is not None
    # 配置表补镜像开关与同步状态列
    added_names = {c.args[1].name for c in add_column.call_args_list}
    assert added_names == _CONFIG_ADDED


def test_downgrade_drops_columns_then_table(monkeypatch) -> None:
    module = _load()
    drop_table, drop_index, drop_column = Mock(), Mock(), Mock()
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    monkeypatch.setattr(module.op, "drop_index", drop_index)
    monkeypatch.setattr(module.op, "drop_column", drop_column)

    module.downgrade()

    dropped_columns = {c.args[1] for c in drop_column.call_args_list}
    assert dropped_columns == _CONFIG_ADDED
    assert drop_table.call_args.args == ("page_table_mirror_records",)
    assert drop_table.call_args.kwargs["schema"] == "safety"


# ── 批次 2：ledger_record_id / 多子表页签 / 隐患到期提醒设置 ──

_BATCH2_CHAIN = [
    # 主线 #156 在 a3c8e5f7b9d1 之后合入 board_prefs 链并以 c9d400000060
    # 合并；本批改接该合并节点保持单链
    ("b7d9e2f4a6c8_add_hazard_ledger_record_id", "b7d9e2f4a6c8", "c9d400000060"),
    (
        "c9f1a5e3b8d2_multi_table_tabs_for_page_mirror",
        "c9f1a5e3b8d2",
        "b7d9e2f4a6c8",
    ),
    (
        "d4e7f1a9c3b5_hazard_due_notify_settings",
        "d4e7f1a9c3b5",
        "c9f1a5e3b8d2",
    ),
]


@pytest.mark.parametrize("name,revision,down", _BATCH2_CHAIN)
def test_batch2_migrations_chain_linearly(name: str, revision: str, down: str) -> None:
    path = _VERSIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == revision
    assert module.down_revision == down


def test_single_head_retains_the_safety_reminder_history() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_VERSIONS.parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(_VERSIONS.parent))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    # c797740130e1：设备 feishu_apps/workshops 链与主线的合并点（单 head）
    assert heads == ["c797740130e1"]
    history = {
        revision.revision for revision in script.walk_revisions(head=heads[0])
    }
    assert "c8e4a2f6d9b3" in history
    assert "d4e7f1a9c3b5" in history


def test_multi_table_tabs_upgrade_adds_columns_and_upgrades_index(monkeypatch) -> None:
    path = _VERSIONS / "c9f1a5e3b8d2_multi_table_tabs_for_page_mirror.py"
    spec = importlib.util.spec_from_file_location("c9f1a5e3b8d2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    add_column, execute, drop_index, create_index = Mock(), Mock(), Mock(), Mock()
    alter_column = Mock()
    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "execute", execute)
    monkeypatch.setattr(module.op, "drop_index", drop_index)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(module.op, "alter_column", alter_column)

    module.upgrade()

    added = {c.args[0] for c in add_column.call_args_list}
    assert added == {"page_feishu_configs", "page_table_mirror_records"}
    # 回填后收紧为非空约束
    assert alter_column.call_args.kwargs.get("nullable") is False
    # 唯一索引升级为三列（page_key, table_id, record_id）
    unique_calls = [c for c in create_index.call_args_list if c.kwargs.get("unique")]
    assert unique_calls
    assert unique_calls[0].args[2] == ["page_key", "table_id", "record_id"]
