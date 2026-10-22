"""设备巡检重构与台账导入相关迁移的 DDL 契约测试。

按 test_fl_line_migrations 的方式加载迁移文件并 mock op，
断言 upgrade/downgrade 只做本需求声明的事：
- c7d1e4f8a2b3：设备表增加出厂编号 / 入厂日期可空列
- d8f2a5b7c4e6：设备表增加数据问题说明可空列
- e9a4c7d1f5b8：删除巡检线路三张表与索引
- f1c7e9a3d4b6：巡检飞书镜像三张表（记录/设备/同步状态）
- a3d8f2c6e1b9：巡检飞书镜像配置表（App Secret 加密存储）
- c4e6f8a0b2d1：台账上传存档表（表格快照 + 导入摘要 + 查询索引）
- c9d400000063：201 二车间拆分为 201-2-MC / 201-2-DR 的数据与授权归一
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
            "drop_constraint", "create_unique_constraint",
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


def test_inspection_feishu_per_workshop_migration(monkeypatch):
    """b4e2f8a1c7d3：巡检四表加 workshop_code，唯一约束改为按车间部分唯一索引。"""
    module = _load("b4e2f8a1c7d3_inspection_feishu_per_workshop.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    # 旧唯一约束全部拆除
    assert mocks["drop_constraint"].call_count == 3
    # 四张表都加 workshop_code（NOT NULL，默认 201-1 回填）
    assert mocks["add_column"].call_count == 4
    added = {call.args[0] for call in mocks["add_column"].call_args_list}
    assert added == {
        "inspection_feishu_config",
        "inspection_feishu_records",
        "inspection_feishu_devices",
        "inspection_feishu_sync_state",
    }
    for call in mocks["add_column"].call_args_list:
        column = call.args[1]
        assert column.name == "workshop_code"
        assert column.nullable is False
        assert column.server_default.arg == "201-1"
    # 4 个部分唯一索引 + 1 个查询索引
    assert mocks["create_index"].call_count == 5
    unique_names = {
        call.args[0]
        for call in mocks["create_index"].call_args_list
        if call.kwargs.get("unique")
    }
    assert unique_names == {
        "uq_inspection_feishu_config_workshop",
        "uq_inspection_feishu_records_source_record",
        "uq_inspection_feishu_devices_record",
        "uq_inspection_feishu_sync_state_ws_table",
    }

    module.downgrade()
    assert mocks["drop_index"].call_count == 5
    assert mocks["drop_column"].call_count == 4
    assert mocks["create_unique_constraint"].call_count == 3


def test_equipment_per_workshop_columns_migration(monkeypatch):
    """c5f9a3b2d8e4：台账/备件/人员三张主表加 workshop_code 与索引。"""
    module = _load("c5f9a3b2d8e4_equipment_per_workshop_columns.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    assert mocks["add_column"].call_count == 3
    added = {call.args[0] for call in mocks["add_column"].call_args_list}
    assert added == {"equipments", "spare_parts", "equipment_personnel"}
    for call in mocks["add_column"].call_args_list:
        column = call.args[1]
        assert column.name == "workshop_code"
        assert column.nullable is False
        assert column.server_default.arg == "201-1"
    assert mocks["create_index"].call_count == 3
    index_names = {call.args[0] for call in mocks["create_index"].call_args_list}
    assert index_names == {
        "ix_equipments_workshop",
        "ix_spare_parts_workshop",
        "ix_equipment_personnel_workshop",
    }

    module.downgrade()
    assert mocks["drop_index"].call_count == 3
    assert mocks["drop_column"].call_count == 3


def test_equipment_ledger_archive_migration(monkeypatch):
    """c4e6f8a0b2d1：台账上传存档表（快照 + 导入摘要 + 查询索引）。"""
    module = _load("c4e6f8a0b2d1_add_equipment_ledger_archives.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    mocks["create_table"].assert_called_once()
    call = mocks["create_table"].call_args
    assert call.args[0] == "equipment_ledger_archives"
    assert call.kwargs["schema"] == "equipment"
    columns = _columns(mocks["create_table"])
    # 表格快照大字段必填；导入摘要允许为空；车间默认与模型一致
    for name in ("rows", "merges", "col_widths"):
        assert columns[name].nullable is False
    assert columns["import_summary"].nullable is True
    assert columns["workshop_code"].nullable is False
    assert columns["workshop_code"].server_default.arg == "201-1"
    # 列表按时间倒序 + 车间过滤两个查询索引
    index_names = {c.args[0] for c in mocks["create_index"].call_args_list}
    assert index_names == {
        "ix_equipment_ledger_archives_created_at",
        "ix_equipment_ledger_archives_workshop_code",
    }

    module.downgrade()
    assert mocks["drop_index"].call_count == 2
    mocks["drop_table"].assert_called_once_with(
        "equipment_ledger_archives", schema="equipment"
    )


def test_inspection_feishu_config_base_url_migration(monkeypatch):
    """飞书配置页：inspection_feishu_config 增加 base_url（完整链接）列。"""
    module = _load("c9d400000062_add_feishu_config_base_url.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    mocks["add_column"].assert_called_once()
    column = mocks["add_column"].call_args.args[1]
    assert column.name == "base_url"
    # 已存行走空串缺省，非空约束不回填
    assert column.nullable is False
    assert column.server_default.arg == ""

    module.downgrade()
    mocks["drop_column"].assert_called_once()
    assert mocks["drop_column"].call_args.args == (
        "inspection_feishu_config",
        "base_url",
    )


def test_split_workshop_201_2_migration(monkeypatch):
    """201 二车间拆分：业务表 201-2 → 201-2-MC，授权 key/visible_sections 同步归一。"""
    module = _load("c9d400000063_split_equipment_workshop_201_2.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    sqls = [call.args[0] for call in mocks["execute"].call_args_list]
    # 3 张无约束表直接改名 + 备件/配置 ×2 + 镜像三表 ×2 + 2 张授权表 × 2 条
    assert len(sqls) == 17
    for table in (
        "equipments",
        "spare_parts",
        "inspection_feishu_config",
        "inspection_feishu_sync_state",
        "equipment_personnel",
        "equipment_ledger_archives",
    ):
        assert any(
            f"equipment.{table}" in sql and "'201-2-MC'" in sql for sql in sqls
        ), table
    # 唯一索引表先软删/删除与既有 MC 行冲突的旧 201-2 行，再改名
    assert any(
        "spare_parts" in sql and "is_deleted = true" in sql for sql in sqls
    )
    assert any(
        "inspection_feishu_records" in sql and sql.startswith("DELETE")
        for sql in sqls
    )
    assert any(
        "role_page_grants" in sql and "workshop-201-2-MC" in sql for sql in sqls
    )
    assert any(
        "user_page_grants" in sql and "visible_sections" in sql for sql in sqls
    )
    # 只改写设备模块授权，不触碰生产模块的 201-2 批次页
    assert all("production" not in sql for sql in sqls)

    mocks["execute"].reset_mock()
    module.downgrade()
    sqls = [call.args[0] for call in mocks["execute"].call_args_list]
    # 镜像表 DR 行删除、配置/备件冲突行软删、MC 归回 201-2、DR 授权移除
    assert any(
        "DELETE FROM equipment.inspection_feishu_records" in sql
        and "'201-2-DR'" in sql
        for sql in sqls
    )
    assert any("is_deleted = true" in sql for sql in sqls)
    assert any("equipment:workshop-201-2-DR" in sql for sql in sqls)
    assert any(
        "'201-2-MC'" in sql and "'201-2'" in sql and "user_page_grants" in sql
        for sql in sqls
    )


def test_create_feishu_apps_migration(monkeypatch):
    """自建应用库表 + 巡检配置 feishu_app_id 引用列。"""
    module = _load("c9d400000064_create_feishu_apps.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()
    mocks["create_table"].assert_called_once()
    table_args = mocks["create_table"].call_args
    assert table_args.args[0] == "feishu_apps"
    assert table_args.kwargs.get("schema") == "equipment"
    columns = _columns(mocks["create_table"])
    assert {"id", "name", "app_id", "app_secret", "is_deleted"} <= set(columns)
    # created_at/updated_at 带数据库默认值（ORM 依赖 server_default 插入）
    assert columns["created_at"].server_default is not None
    assert columns["updated_at"].server_default is not None
    mocks["create_index"].assert_called_once()
    assert mocks["create_index"].call_args.kwargs.get("unique") is True
    mocks["add_column"].assert_called_once()
    add_args = mocks["add_column"].call_args
    assert add_args.args[0] == "inspection_feishu_config"
    assert add_args.args[1].name == "feishu_app_id"
    assert add_args.kwargs.get("schema") == "equipment"

    module.downgrade()
    mocks["drop_column"].assert_called_once_with(
        "inspection_feishu_config", "feishu_app_id", schema="equipment"
    )
    mocks["drop_index"].assert_called_once()
    mocks["drop_table"].assert_called_once_with("feishu_apps", schema="equipment")
