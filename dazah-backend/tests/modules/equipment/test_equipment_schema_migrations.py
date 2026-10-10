"""设备巡检重构与台账导入相关迁移的 DDL 契约测试。

按 test_fl_line_migrations 的方式加载迁移文件并 mock op，
断言 upgrade/downgrade 只做本需求声明的事：
- c7d1e4f8a2b3：设备表增加出厂编号 / 入厂日期可空列
- d8f2a5b7c4e6：设备表增加数据问题说明可空列
- e9a4c7d1f5b8：删除巡检线路三张表与索引
- f1c7e9a3d4b6：巡检飞书镜像三张表（记录/设备/同步状态）
- a3d8f2c6e1b9：巡检飞书镜像配置表（App Secret 加密存储）
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


def _mock_ops(monkeypatch, module) -> dict[str, Mock]:
    mocks = {
        name: Mock()
        for name in (
            "create_table", "create_index", "drop_index", "drop_table",
            "add_column", "drop_column", "execute",
        )
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(module.op, name, mock)
    return mocks


def _columns(create_table: Mock) -> dict:
    return {
        col.name: col for col in create_table.call_args.args[1:] if hasattr(col, "name")
    }


def test_equipment_ledger_columns_migration(monkeypatch):
    module = _load("c7d1e4f8a2b3_add_equipment_factory_no_and_arrival_date.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    assert mocks["add_column"].call_count == 2
    added = {call.args[1].name for call in mocks["add_column"].call_args_list}
    assert added == {"factory_no", "arrival_date"}

    module.downgrade()
    assert mocks["drop_column"].call_count == 2
    dropped = {call.args[1] for call in mocks["drop_column"].call_args_list}
    assert dropped == {"factory_no", "arrival_date"}


def test_equipment_data_issue_note_migration(monkeypatch):
    module = _load("d8f2a5b7c4e6_add_equipment_data_issue_note.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    mocks["add_column"].assert_called_once()
    assert mocks["add_column"].call_args.args[1].name == "data_issue_note"

    module.downgrade()
    mocks["drop_column"].assert_called_once()
    assert mocks["drop_column"].call_args.args[1] == "data_issue_note"


def test_drop_inspection_routes_migration(monkeypatch):
    module = _load("e9a4c7d1f5b8_drop_inspection_routes.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    # 旧巡检任务/记录表去掉线路引用列，六张线路表经 CASCADE 原生 SQL 删除
    assert mocks["drop_column"].call_count == 3
    assert mocks["execute"].call_count == 6
    for call in mocks["execute"].call_args_list:
        assert "DROP TABLE IF EXISTS equipment." in call.args[0]


def test_inspection_feishu_mirror_migration(monkeypatch):
    module = _load("f1c7e9a3d4b6_create_inspection_feishu_mirror.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    created = [call.args[0] for call in mocks["create_table"].call_args_list]
    assert created == [
        "inspection_feishu_records",
        "inspection_feishu_devices",
        "inspection_feishu_sync_state",
    ]
    for call in mocks["create_table"].call_args_list:
        assert call.kwargs["schema"] == "equipment"

    # 记录表（第一个建表调用）保留飞书原始字段快照
    record_call = mocks["create_table"].call_args_list[0]
    assert "raw_fields" in {
        col.name for col in record_call.args[1:] if hasattr(col, "name")
    }

    module.downgrade()
    dropped = [call.args[0] for call in mocks["drop_table"].call_args_list]
    assert dropped == [
        "inspection_feishu_sync_state",
        "inspection_feishu_devices",
        "inspection_feishu_records",
    ]


def test_inspection_feishu_config_migration(monkeypatch):
    module = _load("a3d8f2c6e1b9_create_inspection_feishu_config.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    mocks["create_table"].assert_called_once()
    call = mocks["create_table"].call_args
    assert call.args[0] == "inspection_feishu_config"
    assert call.kwargs["schema"] == "equipment"
    columns = _columns(mocks["create_table"])
    assert columns["app_secret"].nullable is False
    assert "true" in str(columns["is_enabled"].server_default.arg)
    for name in (
        "app_id", "app_token", "today_table_id",
        "history_table_id", "device_table_id",
    ):
        assert columns[name].nullable is False

    module.downgrade()
    mocks["drop_table"].assert_called_once_with(
        "inspection_feishu_config", schema="equipment"
    )
