"""add input_qty to batches

Revision ID: 1bda00eb75cf
Revises: 20260602_0001
Create Date: 2026-06-02 16:37:53.686210
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1bda00eb75cf"
down_revision: str | None = "20260602_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
