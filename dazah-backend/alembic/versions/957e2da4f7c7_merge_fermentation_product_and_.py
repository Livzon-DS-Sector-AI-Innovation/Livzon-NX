"""merge fermentation product and department contact heads

Revision ID: 957e2da4f7c7
Revises: c2f5a8d3e7b1, c9d400000026
Create Date: 2026-09-10 22:11:45.090055
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "957e2da4f7c7"
down_revision: tuple[str, str] = ("c2f5a8d3e7b1", "c9d400000026")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two already-applied schema histories without changing data."""


def downgrade() -> None:
    """Re-expose the two parent heads when the merge revision is downgraded."""
