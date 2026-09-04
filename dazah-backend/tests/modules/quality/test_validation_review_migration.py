"""验证 AI 审核迁移（a7c100000021）的 revision 链与表结构。

覆盖：迁移文件 revision/down_revision、两张表字段与 schema、以及
建表后的基本 CRUD（确保迁移定义与 ORM 模型一致）。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_review import (
    ValidationReviewFile,
    ValidationReviewRecord,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "a7c100000021_quality_validation_reviews.py"
)

_RECORD_COLUMNS = {
    "id",
    "title",
    "review_mode",
    "status",
    "error_message",
    "model_name",
    "input_snapshot",
    "output_payload",
    "job_id",
    "last_generated_at",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
}
_FILE_COLUMNS = {
    "id",
    "review_id",
    "doc_kind",
    "source",
    "file_name",
    "file_type",
    "file_size",
    "storage_key",
    "parsed_text",
    "parse_status",
    "parse_error",
    "sort_order",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
}


def test_migration_revision_chain() -> None:
    """迁移文件必须指向当前唯一 head（e2f3a4b5c6d7），revision 唯一。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "a7c100000021"' in source
    assert 'down_revision: str | None = "e2f3a4b5c6d7"' in source


def test_record_table_schema_and_columns() -> None:
    table = ValidationReviewRecord.__table__
    assert table.schema == "quality"
    assert table.name == "validation_review_records"
    assert _RECORD_COLUMNS.issubset({column.name for column in table.columns})


def test_file_table_schema_and_columns() -> None:
    table = ValidationReviewFile.__table__
    assert table.schema == "quality"
    assert table.name == "validation_review_files"
    assert _FILE_COLUMNS.issubset({column.name for column in table.columns})


@pytest.mark.anyio
async def test_tables_creatable_and_queryable(db_session: AsyncSession) -> None:
    """建表后可插入与查询，验证迁移定义与 ORM 一致。"""
    await db_session.run_sync(
        lambda sync_db: ValidationReviewRecord.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await db_session.run_sync(
        lambda sync_db: ValidationReviewFile.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await db_session.execute(text("DELETE FROM quality.validation_review_files"))
    await db_session.execute(text("DELETE FROM quality.validation_review_records"))

    record = ValidationReviewRecord(
        id=uuid.uuid4(),
        title="迁移测试",
        review_mode="upload",
        status="draft",
    )
    db_session.add(record)
    await db_session.flush()
    row = ValidationReviewFile(
        id=uuid.uuid4(),
        review_id=record.id,
        doc_kind="plan",
        source="upload",
        file_name="VP-test.md",
        file_type="text/markdown",
        file_size=10,
        storage_key="validation-review/test",
        parse_status="pending",
        sort_order=0,
    )
    db_session.add(row)
    await db_session.commit()

    fetched = await db_session.execute(
        select(ValidationReviewRecord).where(
            ValidationReviewRecord.title == "迁移测试"
        )
    )
    record_out = fetched.scalars().first()
    assert record_out is not None
    assert record_out.status == "draft"
    assert record_out.review_mode == "upload"

    file_out = await db_session.execute(
        select(ValidationReviewFile).where(
            ValidationReviewFile.review_id == record.id
        )
    )
    assert file_out.scalars().first() is not None
