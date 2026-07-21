"""merge heads

Revision ID: 4cc0d68d67fe
Revises: 24b7586df7a5, 5f70eb51dfc9
Create Date: 2026-06-06 12:20:44.664607
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cc0d68d67fe'
down_revision: Union[str, None] = ('24b7586df7a5', '5f70eb51dfc9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
