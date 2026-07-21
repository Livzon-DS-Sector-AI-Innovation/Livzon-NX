"""add energy sheet source roles

Revision ID: 15e3b08711ec
Revises: deaa413e8c30
Create Date: 2026-07-13 14:17:12.671197
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15e3b08711ec"
down_revision: str | None = "deaa413e8c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sheet_mappings",
        sa.Column(
            "source_role",
            sa.String(length=32),
            nullable=False,
            server_default="workshop_detail",
            comment="workshop_detail/shared_detail/energy_summary/daily_summary",
        ),
        schema="energy",
    )


def downgrade() -> None:
    op.drop_column("sheet_mappings", "source_role", schema="energy")
