"""merge heads

Revision ID: 4ef5c94be179
Revises: 20260602_0001, 5c291751e3d1
Create Date: 2026-06-05 14:50:05.814304
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "4ef5c94be179"
down_revision: str | None = ("20260602_0001", "5c291751e3d1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
