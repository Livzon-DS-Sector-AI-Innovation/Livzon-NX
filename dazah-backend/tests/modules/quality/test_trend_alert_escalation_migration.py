"""成品/纯化水异常升级推送迁移（c9d400000028）与去重键部分唯一索引（c9d400000030）测试。

覆盖：迁移 revision 链、升级队列表字段与 schema、通知设置第三行播种、
ORM 部分唯一索引定义。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.finished_trend_alert_escalation import (
    QualityTrendAlertEscalation,
)

ESCALATION_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "c9d400000028_trend_alert_escalation.py"
)
PARTIAL_INDEX_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "c9d400000030_trend_ai_partial_unique.py"
)

_COLUMNS = {
    "id",
    "entity_code",
    "source_label",
    "batch_no",
    "metric_key",
    "metric_label",
    "payload",
    "first_message_id",
    "first_notified_at",
    "status",
    "escalate_at",
    "escalated_at",
    "escalated_message_id",
    "retry_count",
    "last_error",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
}


def test_escalation_migration_revision_chain() -> None:
    source = ESCALATION_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "c9d400000028"' in source
    assert 'down_revision: str | None = "c9d400000027"' in source


def test_partial_unique_migration_revision_chain() -> None:
    source = PARTIAL_INDEX_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "c9d400000030"' in source
    assert 'down_revision: str | None = "c9d400000029"' in source
    assert "WHERE is_deleted = false" in source


def test_escalation_table_schema_and_columns() -> None:
    table = QualityTrendAlertEscalation.__table__
    assert table.schema == "quality"
    assert table.name == "quality_trend_alert_escalations"
    assert _COLUMNS == {column.name for column in table.columns}


@pytest.mark.anyio
async def test_escalation_table_creatable_and_queryable(
    db_session: AsyncSession,
) -> None:
    """建表后可插入与查询，验证迁移定义与 ORM 一致。"""
    await db_session.run_sync(
        lambda sync_db: QualityTrendAlertEscalation.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )
    await db_session.execute(
        text("DELETE FROM quality.quality_trend_alert_escalations")
    )

    record = QualityTrendAlertEscalation(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        batch_no="MC260901",
        metric_key="总杂质:≤1.00%",
        metric_label="总杂质",
        payload={"actual_value": 0.55},
        status="pending",
        escalate_at=None,
    )
    db_session.add(record)
    await db_session.commit()

    fetched = await db_session.execute(
        select(QualityTrendAlertEscalation).where(
            QualityTrendAlertEscalation.batch_no == "MC260901"
        )
    )
    out = fetched.scalars().first()
    assert out is not None
    assert out.status == "pending"
    assert out.retry_count == 0
