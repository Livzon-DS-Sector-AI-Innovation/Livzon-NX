"""add actual times to fermentation_batch_actuals

Revision ID: d7e8f9a1b2c3
Revises: c9d400000057
Create Date: 2026-09-28

看板"计划/实际"时间分离：批次实际产量表增加实际移种时刻与
实际放罐时刻两列（分钟精度，可空）。排产值仍来自排产存档，
实际值由罐状态"确认移种"与产量录入顺手记录；历史行缺省
NULL 不受影响。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d7e8f9a1b2c3"
down_revision = "c9d400000057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fermentation_batch_actuals",
        sa.Column(
            "inoculated_at",
            sa.DateTime(),
            nullable=True,
            comment="实际移种时刻（分钟精度，秒恒为 0）",
        ),
        schema="production",
    )
    op.add_column(
        "fermentation_batch_actuals",
        sa.Column(
            "dumped_at",
            sa.DateTime(),
            nullable=True,
            comment="实际放罐时刻（分钟精度，秒恒为 0）",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column(
        "fermentation_batch_actuals",
        "dumped_at",
        schema="production",
    )
    op.drop_column(
        "fermentation_batch_actuals",
        "inoculated_at",
        schema="production",
    )
