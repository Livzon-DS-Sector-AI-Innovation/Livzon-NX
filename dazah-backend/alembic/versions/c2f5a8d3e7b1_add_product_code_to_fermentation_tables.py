"""add product_code to fermentation board tables

Revision ID: c2f5a8d3e7b1
Revises: b7c9e1f4a6d8
Create Date: 2026-09-10

发酵看板多产品数据隔离：排产存档、批次产量、月设置三表增加 product_code
（存量回填 FA）；批次产量与月设置的进行中唯一约束改为产品内唯一。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c2f5a8d3e7b1"
down_revision = "b7c9e1f4a6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_excel_archives",
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
            comment="产品代码（如 FA/MC/DR），存档按产品隔离",
        ),
        schema="production",
    )
    op.create_index(
        "ix_schedule_excel_archives_product_code",
        "schedule_excel_archives",
        ["product_code"],
        schema="production",
    )

    op.add_column(
        "fermentation_batch_actuals",
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
            comment="产品代码（如 FA/MC/DR），产量按产品隔离",
        ),
        schema="production",
    )
    op.drop_index(
        "ux_fermentation_batch_actuals_batch_no",
        table_name="fermentation_batch_actuals",
        schema="production",
    )
    op.create_index(
        "ux_fermentation_batch_actuals_product_batch",
        "fermentation_batch_actuals",
        ["product_code", "batch_no"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )

    op.add_column(
        "fermentation_month_settings",
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
            comment="产品代码（如 FA/MC/DR），设置按产品隔离",
        ),
        schema="production",
    )
    op.drop_index(
        "ux_fermentation_month_settings_period",
        table_name="fermentation_month_settings",
        schema="production",
    )
    op.create_index(
        "ux_fermentation_month_settings_period",
        "fermentation_month_settings",
        ["product_code", "period_start"],
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
    op.create_index(
        "ux_fermentation_month_settings_period",
        "fermentation_month_settings",
        ["period_start"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )
    op.drop_column(
        "fermentation_month_settings", "product_code", schema="production"
    )

    op.drop_index(
        "ux_fermentation_batch_actuals_product_batch",
        table_name="fermentation_batch_actuals",
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
    op.drop_column(
        "fermentation_batch_actuals", "product_code", schema="production"
    )

    op.drop_index(
        "ix_schedule_excel_archives_product_code",
        table_name="schedule_excel_archives",
        schema="production",
    )
    op.drop_column(
        "schedule_excel_archives", "product_code", schema="production"
    )
