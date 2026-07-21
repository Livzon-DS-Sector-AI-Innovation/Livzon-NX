"""merge heads

Revision ID: ca4390627787
Revises: 1e3a6f5002da, 475080fb7682
Create Date: 2026-06-05 16:02:12.042498
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca4390627787'
down_revision: Union[str, None] = ('1e3a6f5002da', '475080fb7682')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
