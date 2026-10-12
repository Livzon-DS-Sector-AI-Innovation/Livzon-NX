"""drop safety.knowledge_articles.update_status

EHS 法规库多维表格中的「更新状态」字段已删除，本地镜像列同步移除。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6b9c2f4a7d3"
down_revision: str | None = "d2f5a8c0e3b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column(
        "knowledge_articles",
        "update_status",
        schema="safety",
    )


def downgrade() -> None:
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "update_status",
            sa.String(length=50),
            nullable=True,
            comment="更新状态（如 新增/已更新）",
        ),
        schema="safety",
    )
