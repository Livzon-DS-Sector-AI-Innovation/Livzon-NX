"""merge workshop chat chain and hazchem msds

Revision ID: 9af3c6bb8778
Revises: ada9041499a5, b9e4f7a2c5d1
Create Date: 2026-10-30 09:07:39.702223
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '9af3c6bb8778'
down_revision: str | None = ('ada9041499a5', 'b9e4f7a2c5d1')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
