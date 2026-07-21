"""merge_heads_20260607_160015

Revision ID: c3a922ec3a1d
Revises: 20260606_0001, 20260607_0001, 7d4e372b86a9, ec4654a030c0
Create Date: 2026-06-07 16:00:15.243350
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a922ec3a1d'
down_revision: Union[str, None] = ('20260606_0001', '20260607_0001', '7d4e372b86a9', 'ec4654a030c0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
