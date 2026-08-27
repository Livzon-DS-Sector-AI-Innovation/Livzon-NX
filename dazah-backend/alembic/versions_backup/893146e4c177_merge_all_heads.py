"""merge_all_heads

Revision ID: 893146e4c177
Revises: 10b95dc75dcd, 62d4ceac12b4, c3a922ec3a1d
Create Date: 2026-06-09 11:16:43.036461
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "893146e4c177"
down_revision: str | None = ("10b95dc75dcd", "62d4ceac12b4", "c3a922ec3a1d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
