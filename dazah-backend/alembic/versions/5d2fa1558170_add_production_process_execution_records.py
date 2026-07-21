"""add production process execution records

Revision ID: 5d2fa1558170
Revises: 266f913b410c
Create Date: 2026-07-15 08:55:46.745777
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d2fa1558170"
down_revision: str | None = "266f913b410c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "process_execution_records",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_no", sa.String(length=128), nullable=False),
        sa.Column(
            "workshop_code",
            sa.String(length=32),
            server_default="203",
            nullable=False,
        ),
        sa.Column("process_code", sa.String(length=32), nullable=False),
        sa.Column("step_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="draft", nullable=False
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source", sa.String(length=32), server_default="manual", nullable=False
        ),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "source",
            "process_code",
            "source_record_id",
            name="uq_process_execution_records_source",
        ),
        schema="production",
    )
    op.create_index(
        "ix_process_execution_records_batch",
        "process_execution_records",
        ["batch_no"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_process_execution_records_process",
        "process_execution_records",
        ["process_code"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_process_execution_records_workshop",
        "process_execution_records",
        ["workshop_code"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_process_execution_records_workshop",
        table_name="process_execution_records",
        schema="production",
    )
    op.drop_index(
        "ix_process_execution_records_process",
        table_name="process_execution_records",
        schema="production",
    )
    op.drop_index(
        "ix_process_execution_records_batch",
        table_name="process_execution_records",
        schema="production",
    )
    op.drop_table("process_execution_records", schema="production")
