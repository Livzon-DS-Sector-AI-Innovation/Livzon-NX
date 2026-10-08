"""add safety.knowledge_articles.local_attachments

本地文档多附件快照列；镜像行附件仍以飞书多维表格为唯一来源。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8d4b6e2c9a1"
down_revision: str | None = "e6b9c2f4a7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "local_attachments",
            sa.JSON(),
            nullable=True,
            comment="本地附件快照 [{token,name,size}]（镜像行附件在飞书维护）",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("knowledge_articles", "local_attachments", schema="safety")
