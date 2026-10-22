"""merge equipment and safety migration heads

Revision ID: e4c1c9548f00
Revises: c8e4a2f6d9b3, c9d400000064
Create Date: 2026-10-22 01:18:09.131479
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4c1c9548f00'
down_revision: Union[str, None] = ('c8e4a2f6d9b3', 'c9d400000064')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
