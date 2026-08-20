"""add_workshop_shift_to_handovers

Revision ID: 6c3d4e5f7a8b
Revises: 5b2c3d4e6f7a
Create Date: 2026-07-06 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6c3d4e5f7a8b"
down_revision: str | None = "5b2c3d4e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shift_handovers",
        sa.Column("workshop", sa.String(length=64), nullable=True),
        schema="production",
    )
    op.add_column(
        "shift_handovers",
        sa.Column("shift", sa.String(length=16), nullable=True),
        schema="production",
    )
    op.create_index(
        "ix_shift_handovers_workshop",
        "shift_handovers",
        ["workshop"],
        unique=False,
        schema="production",
    )
    # 给已有数据填充默认值（可选，这里设为空字符串）
    op.execute(
        "UPDATE production.shift_handovers SET workshop = '', shift = '' WHERE workshop IS NULL OR shift IS NULL"  # noqa: E501
    )
    op.alter_column("shift_handovers", "workshop", nullable=False, schema="production")
    op.alter_column("shift_handovers", "shift", nullable=False, schema="production")


def downgrade() -> None:
    op.drop_index(
        "ix_shift_handovers_workshop", table_name="shift_handovers", schema="production"
    )
    op.drop_column("shift_handovers", "shift", schema="production")
    op.drop_column("shift_handovers", "workshop", schema="production")
