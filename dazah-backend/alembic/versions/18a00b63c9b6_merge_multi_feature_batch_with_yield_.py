"""merge multi feature batch with yield thresholds

Revision ID: 18a00b63c9b6
Revises: c9d3e7a1f5b2, d5fa806e9c40
Create Date: 2026-11-11 12:14:39.983916
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '18a00b63c9b6'
down_revision: str | None = ('c9d3e7a1f5b2', 'd5fa806e9c40')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
