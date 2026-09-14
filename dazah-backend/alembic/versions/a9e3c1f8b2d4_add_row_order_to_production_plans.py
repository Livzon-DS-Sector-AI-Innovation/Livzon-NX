"""add row_order to production_plans

Revision ID: a9e3c1f8b2d4
Revises: c8f5a2d7e4b6
Create Date: 2026-09-14

生产计划台账按飞书原表行序稳定展示：同步时写入 row_order，
历史行缺省 0，列表排序为 车间业务顺序 + row_order。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a9e3c1f8b2d4"
down_revision = "c8f5a2d7e4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "production_plans",
        sa.Column(
            "row_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="飞书表行序（同步写入，用于稳定排序）",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column(
        "production_plans",
        "row_order",
        schema="production",
    )
