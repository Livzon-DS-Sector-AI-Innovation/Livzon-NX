"""merge feature/safety-module and main heads

Revision ID: ccc4c251c6b4
Revises: 24b7586df7a5, 5f70eb51dfc9
Create Date: 2026-06-06 08:36:05.438367
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "ccc4c251c6b4"
down_revision: str | None = ("24b7586df7a5", "5f70eb51dfc9")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
