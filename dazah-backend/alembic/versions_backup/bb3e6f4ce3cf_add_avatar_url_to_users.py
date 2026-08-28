"""add avatar_url to users

Revision ID: bb3e6f4ce3cf
Revises: 4ef5c94be179
Create Date: 2026-06-05 14:56:54.669100
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb3e6f4ce3cf"
down_revision: str | None = "4ef5c94be179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_url", schema="identity")
