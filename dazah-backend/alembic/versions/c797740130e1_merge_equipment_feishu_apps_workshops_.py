"""merge equipment feishu apps workshops with main

Revision ID: c797740130e1
Revises: a3d8c1f6e2b7, d1f2a3b4c5d6
Create Date: 2026-10-26 09:58:44.338106
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'c797740130e1'
down_revision: str | None = ('a3d8c1f6e2b7', 'd1f2a3b4c5d6')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
