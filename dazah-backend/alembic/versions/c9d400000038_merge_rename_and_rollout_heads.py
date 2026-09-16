"""merge mp-mc rename and permission rollout heads

Revision ID: c9d400000038
Revises: c9d400000036, c9d400000037
Create Date: 2026-09-16 18:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c9d400000038"
down_revision: tuple[str, str] = ("c9d400000036", "c9d400000037")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two already-applied schema histories without changing data."""


def downgrade() -> None:
    """Re-expose the two parent heads when the merge revision is downgraded."""
