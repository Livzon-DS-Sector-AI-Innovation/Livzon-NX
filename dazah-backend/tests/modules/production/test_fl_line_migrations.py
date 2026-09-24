"""FL 批次表与停产事件表迁移的 DDL 契约测试。

按 test_capa_plan_department_migration 的方式加载迁移文件并 mock op，
断言 upgrade/downgrade 只做本需求声明的事：
- fl_batches：production schema 建表 + data_month 索引 + 批号部分唯一索引
  （WHERE is_deleted = false，软删除记录不参与唯一约束）
- line_halt_events：production schema 建表 + (product_code, created_at) 索引
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


def _mock_ops(monkeypatch, module) -> tuple[Mock, Mock, Mock, Mock]:
    create_table, create_index = Mock(), Mock()
    drop_index, drop_table = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(module.op, "drop_index", drop_index)
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    return create_table, create_index, drop_index, drop_table


def _columns(create_table: Mock) -> dict:
    return {
        col.name: col for col in create_table.call_args.args[1:] if hasattr(col, "name")
    }


def test_fl_batches_migration_creates_table_with_partial_unique_index(monkeypatch):
    module = _load("c9d400000055_create_fl_batches.py")
    create_table, create_index, drop_index, drop_table = _mock_ops(monkeypatch, module)

    module.upgrade()

    create_table.assert_called_once()
    assert create_table.call_args.args[0] == "fl_batches"
    assert create_table.call_args.kwargs["schema"] == "production"
    columns = _columns(create_table)
    assert columns["batch_no"].nullable is False
    assert columns["batch_no"].type.length == 64
    assert columns["data_month"].type.length == 7

    unique = [c for c in create_index.call_args_list if c.kwargs.get("unique")]
    assert len(unique) == 1
    assert unique[0].args[0] == "uq_fl_batches_batch_no"
    assert unique[0].args[2] == ["batch_no"]
    assert "is_deleted = false" in str(unique[0].kwargs["postgresql_where"])
    assert unique[0].kwargs["schema"] == "production"

    module.downgrade()
    assert drop_index.call_count == 2
    drop_table.assert_called_once_with("fl_batches", schema="production")


def test_line_halt_events_migration_creates_table_and_timeline_index(monkeypatch):
    module = _load("c9d400000056_create_line_halt_events.py")
    create_table, create_index, drop_index, drop_table = _mock_ops(monkeypatch, module)

    module.upgrade()

    create_table.assert_called_once()
    assert create_table.call_args.args[0] == "line_halt_events"
    assert create_table.call_args.kwargs["schema"] == "production"
    columns = _columns(create_table)
    assert columns["product_code"].nullable is False
    assert columns["product_code"].type.length == 16
    assert columns["halted"].nullable is False

    create_index.assert_called_once()
    index_call = create_index.call_args
    assert index_call.args[0] == "ix_line_halt_events_product_created"
    assert index_call.args[2] == ["product_code", "created_at"]
    assert index_call.kwargs["schema"] == "production"

    module.downgrade()
    drop_index.assert_called_once()
    drop_table.assert_called_once_with("line_halt_events", schema="production")
