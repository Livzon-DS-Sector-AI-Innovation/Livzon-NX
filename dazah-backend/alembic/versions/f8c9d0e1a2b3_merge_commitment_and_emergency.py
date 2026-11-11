"""merge safety commitment and emergency plan AI

Revision ID: f8c9d0e1a2b3
Revises: e4c7a1b9d5f3, e5a9c3d7f2b8
Create Date: 2026-11-09 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "f8c9d0e1a2b3"
down_revision: str | Sequence[str] | None = ("e4c7a1b9d5f3", "e5a9c3d7f2b8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
