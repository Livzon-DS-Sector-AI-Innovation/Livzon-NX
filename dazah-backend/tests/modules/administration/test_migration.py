"""行政管理飞书只读镜像迁移 DDL 契约测试。

加载迁移文件并 mock op，断言 upgrade/downgrade 只做本需求声明的事：
建 administration schema、7 张表及其索引；降级逆序删除，不删 schema。
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

MIGRATION_FILE = "a6d3e8c2f7b1_add_administration_feishu_read_mirror.py"
EXPECTED_TABLES = [
    "feishu_configs",
    "feishu_read_source_roots",
    "feishu_read_resources",
    "feishu_read_fields",
    "feishu_read_records",
    "feishu_read_page_bindings",
    "feishu_read_sync_runs",
]


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / f"alembic/versions/{MIGRATION_FILE}"
    spec = importlib.util.spec_from_file_location(
        MIGRATION_FILE.replace(".py", ""), path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_ops(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> dict[str, Mock]:
    mocks = {
        name: Mock()
        for name in (
            "create_table",
            "create_index",
            "drop_index",
            "drop_table",
            "execute",
        )
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(module.op, name, mock)
    return mocks


def test_upgrade_creates_schema_tables_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()

    assert mocks["execute"].call_args_list[0].args[0] == (
        "CREATE SCHEMA IF NOT EXISTS administration"
    )
    created = [call.args[0] for call in mocks["create_table"].call_args_list]
    assert created == EXPECTED_TABLES
    for call in mocks["create_table"].call_args_list:
        assert call.kwargs["schema"] == "administration"
        column_names = {
            col.name for col in call.args[1:] if hasattr(col, "name")
        }
        # BaseModel 公共列必须逐列写出
        assert {"id", "created_at", "updated_at", "is_deleted"} <= column_names
    assert mocks["create_index"].call_count == len(EXPECTED_TABLES)
    assert all(
        call.kwargs["schema"] == "administration"
        for call in mocks["create_index"].call_args_list
    )


def test_config_table_keeps_secret_column_text(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()

    config_call = mocks["create_table"].call_args_list[0]
    columns = {col.name: col for col in config_call.args[1:] if hasattr(col, "name")}
    assert "encrypted_app_secret" in columns
    assert "app_secret" not in columns


def test_downgrade_drops_in_reverse_without_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    mocks = _mock_ops(monkeypatch, module)

    module.downgrade()

    dropped = [call.args[0] for call in mocks["drop_table"].call_args_list]
    assert dropped == list(reversed(EXPECTED_TABLES))
    assert mocks["drop_index"].call_count == len(EXPECTED_TABLES)
    assert mocks["execute"].call_count == 0
