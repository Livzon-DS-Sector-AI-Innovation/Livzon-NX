"""merge equipment plans B/C/E chain with work permits chain

Revision ID: e5b9d2f4a8c7
Revises: d8a3c7e1f5b4, c3a8e5f2b7d4
Create Date: 2026-11-09 10:12:00
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'e5b9d2f4a8c7'
down_revision: str | None = ('d8a3c7e1f5b4', 'c3a8e5f2b7d4')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合并点：两侧迁移各自完成 DDL，此处无数据库操作。"""


def downgrade() -> None:
    """合并点：降级不拆分历史。"""
