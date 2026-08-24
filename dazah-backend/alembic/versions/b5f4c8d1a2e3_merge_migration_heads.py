"""merge the migration and origin/dev production heads

Revision ID: b5f4c8d1a2e3
Revises: 4772bce4935d, 5e1f7a9b0c2d
Create Date: 2026-08-24 16:35:00.000000
"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "b5f4c8d1a2e3"
down_revision: tuple[str, str] = ("4772bce4935d", "5e1f7a9b0c2d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two already-applied schema histories without changing data."""


def downgrade() -> None:
    """Re-expose the two parent heads when the merge revision is downgraded."""
