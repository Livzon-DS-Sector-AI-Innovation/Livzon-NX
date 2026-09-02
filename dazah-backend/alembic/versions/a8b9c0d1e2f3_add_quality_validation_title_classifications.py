"""Add quality validation title classifications table.

Revision ID: a8b9c0d1e2f3
Revises: c2d3e4f5a6b7
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_title_classifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title", sa.Text(), nullable=False, unique=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column(
            "source", sa.String(length=20), nullable=False, server_default="ai"
        ),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column(
            "sample_count", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        comment="验证确认名称的 AI 分类缓存（真实年度台账无验证类别列）",
        schema="quality",
    )
    op.create_index(
        "ix_quality_validation_title_classifications_title",
        "validation_title_classifications",
        ["title"],
        unique=True,
        schema="quality",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_validation_title_classifications_title",
        table_name="validation_title_classifications",
        schema="quality",
    )
    op.drop_table(
        "validation_title_classifications",
        schema="quality",
    )
