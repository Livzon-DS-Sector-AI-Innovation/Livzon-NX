"""看板用户偏好表迁移 DDL 契约测试。

按 test_fl_line_migrations 的方式加载迁移文件并 mock op，断言
upgrade/downgrade 只做本需求声明的事：
- production schema 建表 + user_id 部分唯一索引（软删除不参与唯一）
- 默认值：含中试口径 true、后缀「含中试」
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


def test_board_preferences_migration_creates_table_with_defaults(monkeypatch):
    module = _load("c9d400000059_create_user_board_preferences.py")
    create_table, create_index = Mock(), Mock()
    drop_index, drop_table = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(module.op, "drop_index", drop_index)
    monkeypatch.setattr(module.op, "drop_table", drop_table)

    module.upgrade()

    create_table.assert_called_once()
    assert create_table.call_args.args[0] == "user_board_preferences"
    assert create_table.call_args.kwargs["schema"] == "production"
    columns = {
        col.name: col
        for col in create_table.call_args.args[1:]
        if hasattr(col, "name")
    }
    assert columns["user_id"].nullable is False
    assert columns["avg_pilot_incl"].nullable is False
    assert columns["avg_pilot_incl"].server_default is not None
    assert columns["avg_note"].type.length == 64

    create_index.assert_called_once()
    index_call = create_index.call_args
    assert index_call.args[0] == "uq_user_board_preferences_user"
    assert index_call.args[2] == ["user_id"]
    assert index_call.kwargs.get("unique") is True
    assert "is_deleted = false" in str(index_call.kwargs["postgresql_where"])
    assert index_call.kwargs["schema"] == "production"

    module.downgrade()
    drop_index.assert_called_once()
    drop_table.assert_called_once_with(
        "user_board_preferences", schema="production"
    )
