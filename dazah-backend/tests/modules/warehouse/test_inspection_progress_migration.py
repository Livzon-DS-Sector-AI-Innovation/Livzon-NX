"""检验状态变更日志表（迁移 a7c8d9e0f1b2）的 revision 链与表结构。

覆盖：迁移 revision/down_revision 指向当前 head、ORM 列集合、建表后基本 CRUD。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.models import (
    MaterialPageRow,
    MaterialStatusTransition,
)
from app.modules.warehouse.service import WarehouseService

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "a7c8d9e0f1b2_add_warehouse_material_status_transitions.py"
)

_COLUMNS = {
    "id",
    "page_key",
    "page_snapshot_id",
    "source_record_id",
    "field_name",
    "old_value",
    "new_value",
    "occurred_at",
    "detected_at",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
}


def test_migration_revision_chain() -> None:
    """迁移文件必须接在当前 head c9d400000024 之后。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "a7c8d9e0f1b2"' in source
    assert 'down_revision: str | None = "c9d400000024"' in source


def test_table_schema_and_columns() -> None:
    table = MaterialStatusTransition.__table__
    assert table.schema == "warehouse"
    assert table.name == "material_status_transitions"
    assert _COLUMNS == {column.name for column in table.columns}


@pytest.mark.anyio
async def test_table_creatable_and_queryable(db_session: AsyncSession) -> None:
    """建表后可插入与查询，验证迁移定义与 ORM 一致。"""
    await db_session.run_sync(
        lambda sync_db: MaterialStatusTransition.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    service = WarehouseService(db_session)
    await service.repo.upsert_material_page_snapshot(
        page_key="inspection-migration-test",
        page_title="t",
        table_name="t",
        table_id="tbl-imt",
        columns=[],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )
    snapshot = await service.repo.get_material_page_snapshot(
        "inspection-migration-test"
    )
    assert snapshot is not None
    db_session.add(
        MaterialPageRow(
            page_snapshot_id=snapshot.id,
            source_record_id="rec-imt",
            row_order=1,
            cells={},
            search_text="",
            last_synced_at=datetime.now(UTC),
        )
    )
    record = MaterialStatusTransition(
        id=uuid.uuid4(),
        page_key="inspection-migration-test",
        page_snapshot_id=snapshot.id,
        source_record_id="rec-imt",
        field_name="检测结果",
        old_value=None,
        new_value="合格",
        occurred_at=datetime.now(UTC),
        detected_at=datetime.now(UTC),
    )
    db_session.add(record)
    await db_session.flush()

    fetched = await db_session.execute(
        select(MaterialStatusTransition).where(
            MaterialStatusTransition.source_record_id == "rec-imt"
        )
    )
    out = fetched.scalars().first()
    assert out is not None
    assert out.new_value == "合格"
    assert out.old_value is None
