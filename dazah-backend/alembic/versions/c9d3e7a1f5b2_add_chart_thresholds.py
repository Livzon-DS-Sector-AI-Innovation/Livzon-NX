"""add chart_thresholds

Revision ID: c9d3e7a1f5b2
Revises: b3a6d7e8f902
Create Date: 2026-11-10

仪表盘图表警戒线配置表：按页面范围 + 图表键存一条数值，
各车间收率趋势图/收率卡片的红绿判断读取该值，管理员可调。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c9d3e7a1f5b2"
down_revision = "b3a6d7e8f902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_thresholds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scope_key", sa.String(length=120), nullable=False
        ),
        sa.Column("chart_key", sa.String(length=60), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "scope_key", "chart_key", name="uq_chart_threshold_scope_chart"
        ),
        schema="production",
    )
    op.create_index(
        "ix_chart_thresholds_scope",
        "chart_thresholds",
        ["scope_key"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chart_thresholds_scope",
        table_name="chart_thresholds",
        schema="production",
    )
    op.drop_table("chart_thresholds", schema="production")
