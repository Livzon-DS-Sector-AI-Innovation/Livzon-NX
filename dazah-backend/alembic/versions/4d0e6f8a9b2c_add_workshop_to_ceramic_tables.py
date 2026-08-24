"""add workshop to ceramic tables

Revision ID: 4d0e6f8a9b2c
Revises: 3c9d5e7f8a1b
Create Date: 2026-08-20 12:50:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4d0e6f8a9b2c'
down_revision: str | None = '3c9d5e7f8a1b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "ceramic_membrane_cleans",
    "ceramic_membrane_ops",
    "ceramic_equipment_logs",
    "ceramic_material_separations",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "workshop",
                sa.String(length=32),
                nullable=False,
                server_default="203",
            ),
            schema="production",
        )
        op.create_index(
            f"ix_{table[:20]}_ws",
            table,
            ["workshop"],
            unique=False,
            schema="production",
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table[:20]}_ws", table_name=table, schema="production")
        op.drop_column(table, "workshop", schema="production")
