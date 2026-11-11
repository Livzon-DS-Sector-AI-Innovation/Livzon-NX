"""merge all active heads

Revision ID: b9c8d7e6f5a4
Revises: a6d3e8c2f7b1, f8c9d0e1a2b3
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "b9c8d7e6f5a4"
down_revision: str | Sequence[str] | None = ("a6d3e8c2f7b1", "f8c9d0e1a2b3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
