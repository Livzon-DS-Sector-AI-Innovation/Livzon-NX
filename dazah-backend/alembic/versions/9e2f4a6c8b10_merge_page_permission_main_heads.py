"""merge page-permission and current main migration heads

Revision ID: 9e2f4a6c8b10
Revises: c2d3e4f5a6b7, f7b2d9a4c103
Create Date: 2026-09-02
"""

from collections.abc import Sequence

revision: str = "9e2f4a6c8b10"
down_revision: tuple[str, str] = ("c2d3e4f5a6b7", "f7b2d9a4c103")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the histories without changing schema state."""


def downgrade() -> None:
    """Split back to the two parent heads without changing schema state."""
