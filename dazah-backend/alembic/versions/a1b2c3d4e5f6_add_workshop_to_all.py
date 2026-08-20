"""add_workshop_column_to_all_tables

Revision ID: a1b2c3d4e5f7
Revises: 9c0d1e2f3a4b
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "9c0d1e2f3a4b"

TABLES = [
    "broth_receives",
    "pretreatments",
    "ceramic_feeds",
    "decolor1",
    "filter1",
    "conc1",
    "centrifuge1",
    "recrystallize",
    "filter2",
    "conc2",
    "centrifuge2",
    "dry",
    "pack",
]


def upgrade():
    for t in TABLES:
        op.add_column(
            t,
            sa.Column("workshop", sa.String(32), nullable=False, server_default="203"),
            schema="production",
        )
        op.create_index(
            f"ix_{t[:20]}_ws", t, ["workshop"], unique=False, schema="production"
        )


def downgrade():
    for t in TABLES:
        op.drop_index(f"ix_{t[:20]}_ws", table_name=t, schema="production")
        op.drop_column(t, "workshop", schema="production")
