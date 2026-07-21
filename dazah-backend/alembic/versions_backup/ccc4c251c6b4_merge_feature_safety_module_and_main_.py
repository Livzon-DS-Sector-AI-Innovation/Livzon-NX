"""merge feature/safety-module and main heads

Revision ID: ccc4c251c6b4
Revises: 24b7586df7a5, 5f70eb51dfc9
Create Date: 2026-06-06 08:36:05.438367
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccc4c251c6b4'
down_revision: Union[str, None] = ('24b7586df7a5', '5f70eb51dfc9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
