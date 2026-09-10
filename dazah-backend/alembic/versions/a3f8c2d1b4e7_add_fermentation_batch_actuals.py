"""add fermentation_batch_actuals

Revision ID: a3f8c2d1b4e7
Revises: c9d400000023
Create Date: 2026-09-09

发酵批次实际产量表：支撑发酵车间看板的单批产量图表与历史数据；
同一批次仅允许一条进行中的记录（部分唯一索引），删除采用软删。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a3f8c2d1b4e7"
down_revision = "c9d400000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fermentation_batch_actuals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("batch_no", sa.String(length=64), nullable=False),
        sa.Column("dump_date", sa.Date(), nullable=True),
        sa.Column("yield_kg", sa.Float(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
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
        "ux_fermentation_batch_actuals_batch_no",
        "fermentation_batch_actuals",
        ["batch_no"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ux_fermentation_batch_actuals_batch_no",
        table_name="fermentation_batch_actuals",
        schema="production",
    )
    op.drop_table("fermentation_batch_actuals", schema="production")
