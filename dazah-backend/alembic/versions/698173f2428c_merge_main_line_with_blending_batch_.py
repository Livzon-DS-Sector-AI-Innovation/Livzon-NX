"""merge main line with blending batch width

主线新增迁移与混批字段加宽迁移（b4f2c8d1e3a5）并行开发，
合并为单一 head；本版本不含结构变更。

Revision ID: 698173f2428c
Revises: 8ac71ef51d03, b4f2c8d1e3a5
Create Date: 2026-11-23 17:37:02.986929
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '698173f2428c'
down_revision: str | None = ('8ac71ef51d03', 'b4f2c8d1e3a5')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
