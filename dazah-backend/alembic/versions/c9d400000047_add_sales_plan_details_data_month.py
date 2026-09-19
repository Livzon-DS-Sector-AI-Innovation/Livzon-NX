"""Add data_month to sales plan details for monthly snapshot filtering."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000047"
down_revision: str | None = "c9d400000046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 销售计划执行表按月独立保留快照：数据月份取自源数据表名（如“5月份…”）
    op.add_column(
        "sales_plan_details",
        sa.Column(
            "data_month",
            sa.String(length=7),
            nullable=True,
            comment="数据月份(YYYY-MM)，按源数据表名归属",
        ),
        schema="production",
    )
    op.create_index(
        "ix_sales_plan_data_month",
        "sales_plan_details",
        ["data_month"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sales_plan_data_month",
        table_name="sales_plan_details",
        schema="production",
    )
    op.drop_column("sales_plan_details", "data_month", schema="production")
