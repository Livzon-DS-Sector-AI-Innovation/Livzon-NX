"""add production feishu sync runs

Revision ID: 266f913b410c
Revises: a571e00e39c4
Create Date: 2026-07-14 16:22:15.766874
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "266f913b410c"
down_revision: str | None = "a571e00e39c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "feishu_sync_runs",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_production_feishu_sync_runs_binding",
        "feishu_sync_runs",
        ["binding_id"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_production_feishu_sync_runs_started_at",
        "feishu_sync_runs",
        ["started_at"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_production_feishu_sync_runs_started_at",
        table_name="feishu_sync_runs",
        schema="production",
    )
    op.drop_index(
        "ix_production_feishu_sync_runs_binding",
        table_name="feishu_sync_runs",
        schema="production",
    )
    op.drop_table("feishu_sync_runs", schema="production")
