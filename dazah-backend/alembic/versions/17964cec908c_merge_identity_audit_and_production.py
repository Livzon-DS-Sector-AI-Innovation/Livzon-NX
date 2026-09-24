"""Merge identity audit and production migration branches.

Revision ID: 17964cec908c
Revises: e28d97af109c, c9d400000056
Create Date: 2026-09-24 08:44:09.444027
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "17964cec908c"
down_revision: tuple[str, str] = ("e28d97af109c", "c9d400000056")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
