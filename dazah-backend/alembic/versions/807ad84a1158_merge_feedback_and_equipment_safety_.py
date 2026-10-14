"""merge feedback and equipment safety migrations

Revision ID: 807ad84a1158
Revises: b4e9f3d7a2c0, b8d4f2a6c9e1
Create Date: 2026-10-14 09:39:00.529135
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '807ad84a1158'
down_revision: Union[str, None] = ('b4e9f3d7a2c0', 'b8d4f2a6c9e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
