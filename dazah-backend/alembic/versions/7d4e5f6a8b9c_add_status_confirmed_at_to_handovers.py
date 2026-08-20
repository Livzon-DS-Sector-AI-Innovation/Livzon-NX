"""add_status_confirmed_at_to_handovers

Revision ID: 7d4e5f6a8b9c
Revises: 6c3d4e5f7a8b
Create Date: 2026-07-06 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d4e5f6a8b9c"
down_revision: str | None = "6c3d4e5f7a8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shift_handovers",
        sa.Column("status", sa.String(length=16), nullable=True),
        schema="production",
    )
    op.add_column(
        "shift_handovers",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        schema="production",
    )
    op.execute(
        "UPDATE production.shift_handovers SET status = 'pending' WHERE status IS NULL"
    )
    op.alter_column("shift_handovers", "status", nullable=False, schema="production")


def downgrade() -> None:
    op.drop_column("shift_handovers", "confirmed_at", schema="production")
    op.drop_column("shift_handovers", "status", schema="production")
