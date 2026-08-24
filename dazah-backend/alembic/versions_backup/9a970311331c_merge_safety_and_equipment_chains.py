"""merge safety and equipment chains

Revision ID: 9a970311331c
Revises: 1bda00eb75cf, 1e3a6f5002da
Create Date: 2026-06-03 09:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9a970311331c"
down_revision: str | tuple[str, ...] = ("1bda00eb75cf", "1e3a6f5002da")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
