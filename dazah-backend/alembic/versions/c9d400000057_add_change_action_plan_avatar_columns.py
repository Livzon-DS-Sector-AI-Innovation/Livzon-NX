"""add avatar url columns to quality.quality_change_action_plans"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000057"
down_revision: str | None = "c9d400000056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 变更计划同步从飞书人员字段带出头像 URL，页面人员列展示头像+姓名
    op.add_column(
        "quality_change_action_plans",
        sa.Column("owner_avatar_url", sa.String(length=512), nullable=True),
        schema="quality",
    )
    op.add_column(
        "quality_change_action_plans",
        sa.Column("director_avatar_url", sa.String(length=512), nullable=True),
        schema="quality",
    )


def downgrade() -> None:
    op.drop_column(
        "quality_change_action_plans", "director_avatar_url", schema="quality"
    )
    op.drop_column("quality_change_action_plans", "owner_avatar_url", schema="quality")
