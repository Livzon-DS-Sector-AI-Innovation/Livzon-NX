"""merge safety and equipment chains

Revision ID: 9a970311331c
Revises: 1bda00eb75cf, 1e3a6f5002da
Create Date: 2026-06-03 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9a970311331c"
down_revision: Union[str, tuple[str, ...]] = ("1bda00eb75cf", "1e3a6f5002da")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
