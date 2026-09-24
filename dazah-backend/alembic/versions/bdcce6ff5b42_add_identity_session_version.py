"""add_identity_session_version

Revision ID: bdcce6ff5b42
Revises: c9d400000053
Create Date: 2026-09-22 09:48:48.725280
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bdcce6ff5b42"
down_revision: str | None = "c9d400000053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("users", "session_version", schema="identity")
