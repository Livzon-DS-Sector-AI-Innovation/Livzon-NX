"""页面镜像迁移断言（镜像表 DDL、配置表加列与回退）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

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
