"""add fa_intermediate_records and receiving_task tables

Revision ID: 5e1f7a9b0c2d
Revises: 4d0e6f8a9b2c
Create Date: 2026-08-20 13:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5e1f7a9b0c2d'
down_revision: str | None = '4d0e6f8a9b2c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "fa_intermediate_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("日期", sa.Date(), nullable=True),
        sa.Column("当日母液总体积/方", sa.Float(), nullable=True),
        sa.Column("顶水回流/方6#板框", sa.Float(), nullable=True),
        sa.Column("当日结晶液产母液量（方）", sa.Float(), nullable=True),
        sa.Column("一次离心日用水量（方）", sa.Float(), nullable=True),
        sa.Column("一次甩料车数", sa.Float(), nullable=True),
        sa.Column("离心每车平均用水量（L)160", sa.Float(), nullable=True),
        sa.Column("三效产生一次母液量（方）", sa.Float(), nullable=True),
        sa.Column("三效单车产母液量(L)410", sa.Float(), nullable=True),
        sa.Column("合计570", sa.Float(), nullable=True),
        sa.Column("二次母液总量", sa.Float(), nullable=True),
        sa.Column("二次离心日用水量（方）", sa.Float(), nullable=True),
        sa.Column("二次甩料车数", sa.Float(), nullable=True),
        sa.Column("离心每车平均用水量(L)170左右", sa.Float(), nullable=True),
        sa.Column("合计750", sa.Float(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),  # noqa: E501
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_fa_intermediate_date",
        "fa_intermediate_records",
        ["日期"],
        unique=False,
        schema="production",
    )
    op.create_table(
        "receiving_task",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_no", sa.String(length=64), nullable=False),
        sa.Column("tank_no", sa.String(length=64), nullable=True),
        sa.Column("actual_tank_no", sa.String(length=64), nullable=True),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),  # noqa: E501
        sa.Column("actual_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(length=64), nullable=True),
        sa.Column("delay_reason", sa.String(length=256), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("approver", sa.String(length=64), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),  # noqa: E501
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_receiving_task_batch",
        "receiving_task",
        ["batch_no"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_receiving_task_status",
        "receiving_task",
        ["status"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index("ix_receiving_task_status", table_name="receiving_task", schema="production")  # noqa: E501
    op.drop_index("ix_receiving_task_batch", table_name="receiving_task", schema="production")  # noqa: E501
    op.drop_table("receiving_task", schema="production")
    op.drop_index("ix_fa_intermediate_date", table_name="fa_intermediate_records", schema="production")  # noqa: E501
    op.drop_table("fa_intermediate_records", schema="production")
