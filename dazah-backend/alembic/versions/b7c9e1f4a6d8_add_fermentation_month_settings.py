"""add fermentation_month_settings

Revision ID: b7c9e1f4a6d8
Revises: a3f8c2d1b4e7
Create Date: 2026-09-09

发酵看板扎帐月设置表：本月计划产能等按周期存的设置；
同一周期仅一条进行中记录（部分唯一索引），删除采用软删。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b7c9e1f4a6d8"
down_revision = "a3f8c2d1b4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fermentation_month_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("planned_capacity_kg", sa.Float(), nullable=True),
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
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="production",
    )
    op.create_index(
        "ux_fermentation_month_settings_period",
        "fermentation_month_settings",
        ["period_start"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ux_fermentation_month_settings_period",
        table_name="fermentation_month_settings",
        schema="production",
    )
    op.drop_table("fermentation_month_settings", schema="production")
