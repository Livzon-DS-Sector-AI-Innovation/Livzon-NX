"""add schedule constraints and maintenance recovery date

Revision ID: a3f5b7c9d1e2
Revises: d9e1f2a4b6c8
Create Date: 2026-09-30

排产校验（一期）：新增按产品的排产约束配置表；检修标注增加可选的
预计恢复日期（校验据此把检修窗口内的空位判为合法扰动）。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a3f5b7c9d1e2"
down_revision = "d9e1f2a4b6c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_constraint_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
        ),
        sa.Column("standard_cycle_hours", sa.Float(), nullable=True),
        sa.Column("cycle_tolerance_hours", sa.Float(), nullable=True),
        sa.Column("max_cycle_hours", sa.Float(), nullable=True),
        sa.Column("turnaround_hours", sa.Float(), nullable=True),
        sa.Column("monthly_dump_target", sa.Integer(), nullable=True),
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
            "created_by", sa.Uuid(), sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_by", sa.Uuid(), sa.ForeignKey("identity.users.id"),
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
        "ux_schedule_constraint_settings_product",
        "schedule_constraint_settings",
        ["product_code"],
        unique=True,
        schema="production",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.add_column(
        "tank_maintenance",
        sa.Column("expected_recovery_date", sa.Date(), nullable=True),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column(
        "tank_maintenance",
        "expected_recovery_date",
        schema="production",
    )
    op.drop_index(
        "ux_schedule_constraint_settings_product",
        table_name="schedule_constraint_settings",
        schema="production",
    )
    op.drop_table("schedule_constraint_settings", schema="production")
