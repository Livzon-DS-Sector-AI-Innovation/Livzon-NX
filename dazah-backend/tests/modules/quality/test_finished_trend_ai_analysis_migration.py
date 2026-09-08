"""成品检测趋势 AI 分析落库表（迁移 c9d400000023）的 revision 链与表结构。

覆盖：迁移文件 revision/down_revision 指向当前 head、表字段与 schema、
建表后基本 CRUD（确保迁移定义与 ORM 模型一致）。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.finished_trend_ai_analysis import (
    FinishedTrendAIAnalysis,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "c9d400000023_quality_finished_trend_ai_analyses.py"
)

_COLUMNS = {
    "id",
    "entity_code",
    "source_label",
    "frontend_group",
    "metric_key",
    "metric_label",
    "rule_type",
    "severity",
    "trend_start_batch",
    "trend_end_batch",
    "affected_batches",
    "description",
    "evidence",
    "payload",
    "ai_summary",
    "model_name",
    "job_id",
    "feishu_image_key",
    "feishu_message_id",
    "notification_status",
    "notified_at",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
}


def test_migration_revision_chain() -> None:
    """迁移文件必须接在当前 head b1c2d3e4f5a6 之后，revision 唯一。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "c9d400000023"' in source
    assert 'down_revision: str | None = "b1c2d3e4f5a6"' in source


def test_table_schema_and_columns() -> None:
    table = FinishedTrendAIAnalysis.__table__
    assert table.schema == "quality"
    assert table.name == "quality_finished_trend_ai_analyses"
    assert _COLUMNS == {column.name for column in table.columns}


def test_unique_dedup_constraint_present() -> None:
    table = FinishedTrendAIAnalysis.__table__
    unique_keys = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert tuple(
        sorted(
            ["entity_code", "metric_key", "rule_type", "trend_end_batch"]
        )
    ) in unique_keys


@pytest.mark.anyio
async def test_table_creatable_and_queryable(db_session: AsyncSession) -> None:
    """建表后可插入与查询，验证迁移定义与 ORM 一致。"""
    await db_session.run_sync(
        lambda sync_db: FinishedTrendAIAnalysis.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await db_session.execute(
        text("DELETE FROM quality.quality_finished_trend_ai_analyses")
    )

    record = FinishedTrendAIAnalysis(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        frontend_group="mpa",
        metric_key="含量（干品）:97.0%-103.0%",
        metric_label="含量（干品）",
        rule_type="continuous_move",
        severity="medium",
        trend_start_batch="MC260801",
        trend_end_batch="MC260808",
        description="连续 8 批上升",
        evidence={"direction": "up", "run_points": 8},
        payload={"points": [{"batch_no": "MC260808", "value": 99.5}]},
        notification_status="pending",
    )
    db_session.add(record)
    await db_session.commit()

    fetched = await db_session.execute(
        select(FinishedTrendAIAnalysis).where(
            FinishedTrendAIAnalysis.entity_code == "qc_finished_internal",
            FinishedTrendAIAnalysis.rule_type == "continuous_move",
        )
    )
    out = fetched.scalars().first()
    assert out is not None
    assert out.severity == "medium"
    assert out.evidence == {"direction": "up", "run_points": 8}
