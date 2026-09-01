"""add quality historical deviations and deviation workbench tables

历史偏差台账（quality.historical_deviations）、偏差工作台提示词配置
（quality.deviation_workbench_settings）与工作台记录台账
（quality.deviation_workbench_reports）。编号字段均使用部分唯一索引
（WHERE is_deleted = false），保证软删后同编号可复用。

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLUMNS = [
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
    sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("historical_deviations", schema="quality"):
        op.create_table(
            "historical_deviations",
            sa.Column("code", sa.String(length=255), nullable=False),
            sa.Column("deviation_event", sa.Text(), nullable=True),
            sa.Column("deviation_content", sa.Text(), nullable=True),
            sa.Column("direct_cause", sa.Text(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("investigation_conclusion", sa.Text(), nullable=True),
            sa.Column("attachments", sa.JSON(), nullable=True),
            sa.Column("ai_extract_payload", sa.JSON(), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("deleted_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            *_BASE_COLUMNS,
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
    if not inspector.has_table("deviation_workbench_settings", schema="quality"):
        op.create_table(
            "deviation_workbench_settings",
            sa.Column(
                "report_system_prompt",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
            *_BASE_COLUMNS,
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
    if not inspector.has_table("deviation_workbench_reports", schema="quality"):
        op.create_table(
            "deviation_workbench_reports",
            sa.Column("code", sa.String(length=255), nullable=False),
            sa.Column(
                "source_type",
                sa.String(length=50),
                nullable=False,
                server_default="manual",
            ),
            sa.Column("source_record_id", sa.String(length=100), nullable=True),
            sa.Column("deviation_summary", sa.Text(), nullable=True),
            sa.Column("manual_text", sa.Text(), nullable=True),
            sa.Column("attachments", sa.JSON(), nullable=True),
            sa.Column("context_snapshot", sa.JSON(), nullable=True),
            sa.Column("report_payload", sa.JSON(), nullable=True),
            sa.Column("report_md", sa.Text(), nullable=True),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column(
                "status",
                sa.String(length=50),
                nullable=False,
                server_default="processing",
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("deleted_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            *_BASE_COLUMNS,
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )

    # 部分唯一索引：仅约束未删除行（编号软删后可复用）
    op.create_index(
        "uq_quality_historical_deviations_code",
        "historical_deviations",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="quality",
    )
    op.create_index(
        "uq_quality_deviation_workbench_reports_code",
        "deviation_workbench_reports",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="quality",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("deviation_workbench_reports", schema="quality"):
        op.drop_index(
            "uq_quality_deviation_workbench_reports_code",
            table_name="deviation_workbench_reports",
            schema="quality",
        )
        op.drop_table("deviation_workbench_reports", schema="quality")
    if inspector.has_table("deviation_workbench_settings", schema="quality"):
        op.drop_table("deviation_workbench_settings", schema="quality")
    if inspector.has_table("historical_deviations", schema="quality"):
        op.drop_index(
            "uq_quality_historical_deviations_code",
            table_name="historical_deviations",
            schema="quality",
        )
        op.drop_table("historical_deviations", schema="quality")
