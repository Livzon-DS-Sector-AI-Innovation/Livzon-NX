"""merge repair ledger tables with main line

设备检修台账迁移（8910770ab796）与主线（含 #238 的合并版本）并行开发，
合并为单一 head；本版本不含结构变更。

Revision ID: b098d78d072c
Revises: 698173f2428c, 8910770ab796
Create Date: 2026-11-23 18:12:13.629379
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'b098d78d072c'
down_revision: str | None = ('698173f2428c', '8910770ab796')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
