"""add quality_finished_trend_ai_analyses table

成品检测趋势 AI 分析落库表：存确定性趋势规则（连续上升/下降、斜率突变、
均值台阶偏移、月环比）产出的异常事实 + 可选 LLM 结论 + 重渲染序列快照 +
推送/去重状态。业务唯一键 (entity_code, metric_key, rule_type,
trend_end_batch) 作去重，避免重复打开仪表盘时重复分析/推送/计费。

Revision ID: c9d400000023
Revises: c9d400000022
Create Date: 2026-09-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000023"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table(
        "quality_finished_trend_ai_analyses", schema="quality"
    ):
        op.create_table(
            "quality_finished_trend_ai_analyses",
            sa.Column("entity_code", sa.String(length=64), nullable=False),
            sa.Column("source_label", sa.String(length=128), nullable=True),
            sa.Column("frontend_group", sa.String(length=32), nullable=True),
            sa.Column("metric_key", sa.String(length=256), nullable=False),
            sa.Column("metric_label", sa.String(length=256), nullable=False),
            sa.Column("rule_type", sa.String(length=32), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("trend_start_batch", sa.String(length=128), nullable=True),
            sa.Column("trend_end_batch", sa.String(length=128), nullable=False),
            sa.Column("affected_batches", sa.JSON(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("ai_summary", sa.JSON(), nullable=True),
            sa.Column("model_name", sa.String(length=128), nullable=True),
            sa.Column("job_id", sa.String(length=128), nullable=True),
            sa.Column("feishu_image_key", sa.String(length=256), nullable=True),
            sa.Column("feishu_message_id", sa.String(length=128), nullable=True),
            sa.Column(
                "notification_status",
                sa.String(length=32),
                server_default="pending",
                nullable=False,
            ),
            sa.Column(
                "notified_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column(
                "is_deleted", sa.Boolean(), server_default="false", nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "entity_code",
                "metric_key",
                "rule_type",
                "trend_end_batch",
                name="uq_quality_finished_trend_ai_analysis_key",
            ),
            schema="quality",
        )
        op.create_index(
            "ix_quality_finished_trend_ai_analysis_entity_metric",
            "quality_finished_trend_ai_analyses",
            ["entity_code", "metric_key"],
            schema="quality",
        )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_finished_trend_ai_analysis_entity_metric",
        table_name="quality_finished_trend_ai_analyses",
        schema="quality",
    )
    op.drop_table("quality_finished_trend_ai_analyses", schema="quality")
