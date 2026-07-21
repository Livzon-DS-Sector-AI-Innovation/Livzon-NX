"""make production feishu table id optional

Revision ID: a7c100000020
Revises: a7c100000019
Create Date: 2026-07-08 00:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000020"
down_revision: str | None = "a7c100000019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "feishu_configs",
        "table_id",
        existing_type=sa.String(length=128),
        nullable=True,
        schema="production",
    )


def downgrade() -> None:
    op.alter_column(
        "feishu_configs",
        "table_id",
        existing_type=sa.String(length=128),
        nullable=False,
        schema="production",
    )
