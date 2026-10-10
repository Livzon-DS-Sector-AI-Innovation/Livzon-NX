"""排产约束配置与排产草稿记录迁移的 DDL 契约测试。

按 test_fl_line_migrations 的方式加载迁移文件并 mock op，
断言 upgrade/downgrade 只做本需求声明的事：
- schedule_constraint_settings：production schema 建表 +
  product_code 部分唯一索引（WHERE is_deleted = false）+
  tank_maintenance 增加 expected_recovery_date 可空列
- schedule_draft_records：production schema 建表 +
  (product_code, params_hash) 普通索引
"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def _load(file_name: str):
    path = Path(__file__).resolve().parents[3] / f"alembic/versions/{file_name}"
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_ops(monkeypatch, module) -> tuple[Mock, Mock, Mock, Mock, Mock, Mock]:
    create_table, create_index = Mock(), Mock()
    drop_index, drop_table = Mock(), Mock()
    add_column, drop_column = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(module.op, "drop_index", drop_index)
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "drop_column", drop_column)
    return create_table, create_index, drop_index, drop_table, add_column, drop_column


def _columns(create_table: Mock) -> dict:
    return {
        col.name: col for col in create_table.call_args.args[1:] if hasattr(col, "name")
    }


def test_schedule_constraints_migration_creates_table_and_recovery_column(
    monkeypatch,
):
    module = _load("a3f5b7c9d1e2_add_schedule_constraints_and_maintenance_recovery.py")
    (
        create_table, create_index, drop_index, drop_table, add_column, drop_column,
    ) = _mock_ops(monkeypatch, module)

    module.upgrade()

    create_table.assert_called_once()
    assert create_table.call_args.args[0] == "schedule_constraint_settings"
    assert create_table.call_args.kwargs["schema"] == "production"
    columns = _columns(create_table)
    assert columns["product_code"].nullable is False
    assert columns["product_code"].server_default.arg == "FA"
    assert columns["standard_cycle_hours"].nullable is True

    create_index.assert_called_once()
    call = create_index.call_args
    assert call.args[0] == "ux_schedule_constraint_settings_product"
    assert call.kwargs["unique"] is True
    assert call.args[2] == ["product_code"]
    assert "is_deleted = false" in str(call.kwargs["postgresql_where"])
    assert call.kwargs["schema"] == "production"

    add_column.assert_called_once()
    assert add_column.call_args.args[0] == "tank_maintenance"
    assert add_column.call_args.args[1].name == "expected_recovery_date"
    assert add_column.call_args.kwargs["schema"] == "production"

    module.downgrade()
    drop_column.assert_called_once()
    assert drop_column.call_args.args[0] == "tank_maintenance"
    assert drop_column.call_args.args[1] == "expected_recovery_date"
    drop_index.assert_called_once()
    drop_table.assert_called_once_with(
        "schedule_constraint_settings", schema="production"
    )


def test_schedule_draft_records_migration_creates_table_and_hash_index(monkeypatch):
    module = _load("b4c8d2e6f9a1_add_schedule_draft_records.py")
    create_table, create_index, drop_index, drop_table, _, _ = _mock_ops(
        monkeypatch, module
    )

    module.upgrade()

    create_table.assert_called_once()
    assert create_table.call_args.args[0] == "schedule_draft_records"
    assert create_table.call_args.kwargs["schema"] == "production"
    columns = _columns(create_table)
    assert columns["product_code"].nullable is False
    assert columns["params_hash"].nullable is False
    assert columns["params_hash"].type.length == 32
    assert columns["file_name"].type.length == 255

    create_index.assert_called_once()
    call = create_index.call_args
    assert call.args[0] == "ix_schedule_draft_records_hash"
    assert call.args[2] == ["product_code", "params_hash"]
    assert not call.kwargs.get("unique")
    assert call.kwargs["schema"] == "production"

    module.downgrade()
    drop_index.assert_called_once()
    drop_table.assert_called_once_with("schedule_draft_records", schema="production")
