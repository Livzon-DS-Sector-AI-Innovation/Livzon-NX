"""merge security repair and safety responsibility history

Revision ID: b8d2f4a6c0e9
Revises: a7c3e5f1b8d2, f4a6c8e0b2d5
Create Date: 2026-10-29 13:28:52.587789
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b8d2f4a6c0e9"
down_revision: tuple[str, str] = ("a7c3e5f1b8d2", "f4a6c8e0b2d5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Join revision histories only; both parent migrations retain their objects.
    pass


def downgrade() -> None:
    # Splitting the revision histories must not delete existing data or schema.
    pass
