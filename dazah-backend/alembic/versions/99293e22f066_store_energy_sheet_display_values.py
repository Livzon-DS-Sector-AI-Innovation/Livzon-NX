"""store energy sheet display values

Revision ID: 99293e22f066
Revises: a6d4c8e2f901
Create Date: 2026-07-21 07:34:17.133249
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "99293e22f066"
down_revision: str | None = "a6d4c8e2f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "snapshot_rows",
        sa.Column(
            "display_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="飞书按单元格格式渲染后的显示值",
        ),
        schema="energy",
    )


def downgrade() -> None:
    op.drop_column("snapshot_rows", "display_values", schema="energy")
