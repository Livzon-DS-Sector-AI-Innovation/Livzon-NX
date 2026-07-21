"""add quality ai logs

Revision ID: a7c100000003
Revises: a7c100000002
Create Date: 2026-06-30 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000003"
down_revision: str | None = "a7c100000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    op.add_column(
        "quality_change_controls",
        sa.Column("impact_assessment", sa.Text(), nullable=True),
        schema="quality",
    )
    op.create_table(
        "quality_ai_analysis_logs",
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_type", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "is_applied", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.Uuid(), nullable=True),
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
        schema="quality",
    )


def downgrade() -> None:
    op.drop_table("quality_ai_analysis_logs", schema="quality")
    op.drop_column("quality_change_controls", "impact_assessment", schema="quality")