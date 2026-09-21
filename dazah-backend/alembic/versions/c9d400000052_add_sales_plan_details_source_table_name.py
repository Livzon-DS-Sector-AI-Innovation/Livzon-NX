"""Add source_table_name to sales plan details for feishu source tracing."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000052"
down_revision: str | None = "c9d400000051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 记录每行数据来源的飞书数据表名（如“5月份销售计划执行表”），供前端展示
    op.add_column(
        "sales_plan_details",
        sa.Column(
            "source_table_name",
            sa.String(length=255),
            nullable=True,
            comment="来源飞书数据表名（同步时写入）",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column(
        "sales_plan_details", "source_table_name", schema="production"
    )
