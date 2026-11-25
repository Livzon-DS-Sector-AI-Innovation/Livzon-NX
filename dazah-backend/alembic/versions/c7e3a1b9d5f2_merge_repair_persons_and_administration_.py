"""merge repair persons with administration notices

检修记录人员列迁移（db1d4d7f5632）与主线公告通知台账迁移（b6d8a2e4c9f1）
并行开发，合并为单一 head；本版本不含结构变更。

Revision ID: c7e3a1b9d5f2
Revises: b6d8a2e4c9f1, db1d4d7f5632
Create Date: 2026-11-25 09:22:03.020173
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'c7e3a1b9d5f2'
down_revision: str | None = ('b6d8a2e4c9f1', 'db1d4d7f5632')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
