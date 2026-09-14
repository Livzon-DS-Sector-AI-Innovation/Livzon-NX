"""merge extraction reports and quality mirror heads

Revision ID: f73ddeb82366
Revises: a9e3c1f8b2d4, c9d400000032
Create Date: 2026-09-14 16:26:36.784583
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f73ddeb82366"
down_revision: tuple[str, str] = ("a9e3c1f8b2d4", "c9d400000032")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two already-applied schema histories without changing data."""


def downgrade() -> None:
    """Re-expose the two parent heads when the merge revision is downgraded."""
