"""Add material source sync progress columns.

Revision ID: f5e4d3c2b1a0
Revises: e6a7b8c9d0e1
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5e4d3c2b1a0"
down_revision: str | None = "e6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_total_records",
            sa.Integer(),
            nullable=True,
            comment="本次同步飞书侧预计记录数（同步进行中）",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_fetched_count",
            sa.Integer(),
            nullable=True,
            comment="本次同步已拉取记录数（同步进行中）",
        ),
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_column(
        "material_source_configs",
        "sync_fetched_count",
        schema="procurement",
    )
    op.drop_column(
        "material_source_configs",
        "sync_total_records",
        schema="procurement",
    )
