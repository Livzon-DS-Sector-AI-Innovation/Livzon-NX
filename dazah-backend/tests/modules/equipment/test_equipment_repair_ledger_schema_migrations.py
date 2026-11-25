"""设备检修台账相关迁移的 DDL 契约测试。

按 test_equipment_schema_migrations 的方式加载迁移文件并 mock op，
断言 upgrade/downgrade 只做本需求声明的事：
- 8910770ab796：检修飞书镜像三张表（记录 / 同步状态 / 配置）与四个索引
- b098d78d072c：与主线的合并版本，不含结构变更

同时在独立测试库上验证「仅未删除记录唯一」的部分唯一索引语义。
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.repair_ledger import RepairRecord

MERGE_HEAD = "b098d78d072c"
PERSONS_COLUMN_REVISION = "db1d4d7f5632"
MERGE_WITH_MAIN = "698173f2428c"
REPAIR_TABLES_REVISION = "8910770ab796"


def _load(file_name: str):
    path = Path(__file__).resolve().parents[3] / f"alembic/versions/{file_name}"
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _mock_ops(monkeypatch, module) -> dict[str, Mock]:
    names = (
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
        "add_column",
        "drop_column",
        "execute",
        "drop_constraint",
        "create_unique_constraint",
        "create_foreign_key",
    )
    mocks = {name: Mock() for name in names}
    target = getattr(module, "op", None)
    if target is None:
        # 合并版本不导入 op：注入同名桩，确认 upgrade/downgrade 不触碰数据库
        target = SimpleNamespace()
        monkeypatch.setattr(module, "op", target, raising=False)
    for name, mock in mocks.items():
        monkeypatch.setattr(target, name, mock, raising=False)
    return mocks


def test_repair_ledger_tables_migration(monkeypatch):
    module = _load("8910770ab796_equipment_repair_ledger_mirror_tables.py")
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()

    # 只建本需求的三张表，全部落在 equipment schema；不触碰其他模块的表
    assert module.revision == REPAIR_TABLES_REVISION
    assert [call.kwargs["schema"] for call in mocks["create_table"].call_args_list] == [
        "equipment",
        "equipment",
        "equipment",
    ]
    created = {call.args[0]: call for call in mocks["create_table"].call_args_list}
    assert set(created) == {
        "repair_records",
        "repair_sync_state",
        "repair_feishu_config",
    }
    for destructive in ("drop_table", "add_column", "drop_column", "execute"):
        assert mocks[destructive].call_count == 0, destructive

    records_columns = {
        col.name for col in created["repair_records"].args[1:] if hasattr(col, "name")
    }
    assert {
        "workshop_code",
        "record_id",
        "workshop_text",
        "equipment_text",
        "repaired_at",
        "person_text",
        "fault_desc",
        "spare_parts",
        "result",
        "remark",
        "raw_fields",
        "last_modified_at",
    } <= records_columns

    # 同车间同飞书记录仅对未删除行唯一；车间配置与同步状态每车间一行
    indexes = {call.args[0]: call for call in mocks["create_index"].call_args_list}
    assert set(indexes) == {
        "ix_repair_records_workshop_date",
        "uq_repair_records_source_record",
        "uq_repair_sync_state_workshop",
        "uq_repair_feishu_config_workshop",
    }
    for name in (
        "uq_repair_records_source_record",
        "uq_repair_sync_state_workshop",
        "uq_repair_feishu_config_workshop",
    ):
        assert indexes[name].kwargs["unique"] is True
        assert str(indexes[name].kwargs["postgresql_where"]) == "is_deleted = false"

    for call in mocks["create_index"].call_args_list:
        assert call.kwargs["schema"] == "equipment"


def test_repair_ledger_tables_migration_downgrade_only_drops_its_own(monkeypatch):
    module = _load("8910770ab796_equipment_repair_ledger_mirror_tables.py")
    mocks = _mock_ops(monkeypatch, module)

    module.downgrade()

    assert [call.args[0] for call in mocks["drop_table"].call_args_list] == [
        "repair_feishu_config",
        "repair_sync_state",
        "repair_records",
    ]
    assert {call.args[0] for call in mocks["drop_index"].call_args_list} == {
        "uq_repair_feishu_config_workshop",
        "uq_repair_sync_state_workshop",
        "uq_repair_records_source_record",
        "ix_repair_records_workshop_date",
    }
    for call in mocks["drop_table"].call_args_list + mocks["drop_index"].call_args_list:
        assert call.kwargs["schema"] == "equipment"
    for untouched in (
        "create_table",
        "create_index",
        "add_column",
        "drop_column",
        "execute",
    ):
        assert mocks[untouched].call_count == 0, untouched


def test_repair_ledger_merge_revision_has_no_schema_change(monkeypatch):
    module = _load("b098d78d072c_merge_repair_ledger_tables_with_main_.py")
    mocks = _mock_ops(monkeypatch, module)

    assert module.revision == MERGE_HEAD
    # 合并版本把主线合并点与检修表迁移并为一条线
    assert set(module.down_revision) == {MERGE_WITH_MAIN, REPAIR_TABLES_REVISION}

    module.upgrade()
    module.downgrade()
    assert all(mock.call_count == 0 for mock in mocks.values())


def test_migration_history_has_the_merge_as_its_single_head():
    config = Config(str(_backend_root() / "alembic.ini"))
    config.set_main_option("script_location", str(_backend_root() / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [PERSONS_COLUMN_REVISION]
    revisions = {revision.revision for revision in script.walk_revisions()}
    assert {
        REPAIR_TABLES_REVISION,
        MERGE_WITH_MAIN,
        MERGE_HEAD,
        "b4f2c8d1e3a5",
    } <= revisions


async def test_repair_record_is_unique_per_workshop_only_while_not_deleted(
    db_session: AsyncSession,
):
    """部分唯一索引：同一飞书记录只允许一个有效行；软删除后可重新写入。"""
    workshop = "t-uq-001"

    async with db_session.begin_nested():
        db_session.add(
            RepairRecord(
                workshop_code=workshop, record_id="rec-dup", equipment_text="离心泵A"
            )
        )
        await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                RepairRecord(
                    workshop_code=workshop,
                    record_id="rec-dup",
                    equipment_text="离心泵B",
                )
            )
            await db_session.flush()

    await db_session.execute(
        update(RepairRecord)
        .where(
            RepairRecord.workshop_code == workshop, RepairRecord.record_id == "rec-dup"
        )
        .values(is_deleted=True)
    )
    async with db_session.begin_nested():
        db_session.add(
            RepairRecord(
                workshop_code=workshop, record_id="rec-dup", equipment_text="离心泵C"
            )
        )
        await db_session.flush()

    rows = (
        (
            await db_session.execute(
                select(RepairRecord).where(RepairRecord.workshop_code == workshop)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(row.equipment_text or "" for row in rows) == ["离心泵A", "离心泵C"]
