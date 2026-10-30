"""merge workshop feishu chat id chain and main

Revision ID: ada9041499a5
Revises: da5f78a06d60, b8d2f4a6c0e9
Create Date: 2026-10-29 17:12:58.671732
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'ada9041499a5'
down_revision: str | None = ('da5f78a06d60', 'b8d2f4a6c0e9')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
