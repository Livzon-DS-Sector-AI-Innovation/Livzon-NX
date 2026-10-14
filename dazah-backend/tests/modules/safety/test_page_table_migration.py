"""页面表格绑定迁移断言（DDL、schema、部分唯一索引与回退）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

_VERSIONS = Path(__file__).resolve().parents[3] / "alembic/versions"
_NAME = "c5d7e9a1b3f4_create_safety_page_feishu_configs"

_COLUMNS = {
    "page_key",
    "app_token",
    "table_id",
    "view_id",
    "hidden_field_names",
    "is_enabled",
    "last_test_status",
    "last_test_error",
    "last_tested_at",
    "last_test_field_count",
    "last_test_record_count",
}


def _load():
    path = _VERSIONS / f"{_NAME}.py"
    spec = importlib.util.spec_from_file_location(_NAME, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_from_current_head() -> None:
    module = _load()
    assert module.revision == "c5d7e9a1b3f4"
    # 主线在 d9e1f2a4b6c8 之后并行合入设备按车间隔离迁移（c5f9a3b2d8e4），
    # 本批改接在主线头之后，保持单链（见迁移文件内注释）
    assert module.down_revision == "c5f9a3b2d8e4"


def test_upgrade_creates_table_with_partial_unique_index(monkeypatch) -> None:
    module = _load()
    create_table, create_index = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)

    module.upgrade()

    assert create_table.call_args.args[0] == "page_feishu_configs"
    assert create_table.call_args.kwargs["schema"] == "safety"
    column_names = {
        arg.name for arg in create_table.call_args.args[1:] if hasattr(arg, "name")
    }
    assert _COLUMNS.issubset(column_names)
    # 软删除表：page_key 用部分唯一索引，避免软删后重建同 key 冲突
    assert create_index.call_args.args[:3] == (
        "uq_safety_page_feishu_configs_page_key",
        "page_feishu_configs",
        ["page_key"],
    )
    assert create_index.call_args.kwargs["unique"] is True
    assert create_index.call_args.kwargs["schema"] == "safety"
    assert create_index.call_args.kwargs["postgresql_where"] is not None


def test_downgrade_drops_index_then_table(monkeypatch) -> None:
    module = _load()
    drop_table, drop_index = Mock(), Mock()
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    monkeypatch.setattr(module.op, "drop_index", drop_index)

    module.downgrade()

    assert drop_index.call_args.args[0] == "uq_safety_page_feishu_configs_page_key"
    assert drop_index.call_args.kwargs["schema"] == "safety"
    assert drop_table.call_args.args == ("page_feishu_configs",)
    assert drop_table.call_args.kwargs["schema"] == "safety"
