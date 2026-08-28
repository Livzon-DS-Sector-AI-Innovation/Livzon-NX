"""add batch lineage tables

Revision ID: 3c9d5e7f8a1b
Revises: 7d8e74c81962
Create Date: 2026-08-20 12:45:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3c9d5e7f8a1b'
down_revision: str | None = '7d8e74c81962'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "batch_lineage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upstream_type", sa.String(length=32), nullable=False),
        sa.Column("upstream_batch", sa.String(length=64), nullable=False),
        sa.Column("downstream_type", sa.String(length=32), nullable=False),
        sa.Column("downstream_batch", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_batch_lineage_upstream",
        "batch_lineage",
        ["upstream_type", "upstream_batch"],
        schema="production",
    )
    op.create_index(
        "ix_batch_lineage_downstream",
        "batch_lineage",
        ["downstream_type", "downstream_batch"],
        schema="production",
    )
    op.create_table(
        "fa_batch_lineage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upstream_type", sa.String(length=32), nullable=False),
        sa.Column("upstream_batch", sa.String(length=64), nullable=False),
        sa.Column("downstream_type", sa.String(length=32), nullable=False),
        sa.Column("downstream_batch", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_fa_batch_lineage_upstream",
        "fa_batch_lineage",
        ["upstream_type", "upstream_batch"],
        schema="production",
    )
    op.create_index(
        "ix_fa_batch_lineage_downstream",
        "fa_batch_lineage",
        ["downstream_type", "downstream_batch"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index("ix_fa_batch_lineage_downstream", table_name="fa_batch_lineage", schema="production")  # noqa: E501
    op.drop_index("ix_fa_batch_lineage_upstream", table_name="fa_batch_lineage", schema="production")  # noqa: E501
    op.drop_table("fa_batch_lineage", schema="production")
    op.drop_index("ix_batch_lineage_downstream", table_name="batch_lineage", schema="production")  # noqa: E501
    op.drop_index("ix_batch_lineage_upstream", table_name="batch_lineage", schema="production")  # noqa: E501
    op.drop_table("batch_lineage", schema="production")
