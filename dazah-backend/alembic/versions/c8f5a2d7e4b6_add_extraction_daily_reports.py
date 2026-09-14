"""add extraction_daily_reports

Revision ID: c8f5a2d7e4b6
Revises: b5d2e8a4c6f9
Create Date: 2026-09-11

提炼工段成品日报表：按日记录成品产量，与批次台账相互独立（方案 B）；
同产品同一天仅一条进行中记录（部分唯一索引），重复录入覆盖更新，软删。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c8f5a2d7e4b6"
down_revision = "b5d2e8a4c6f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_daily_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("quantity_kg", sa.Float(), nullable=False),
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
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
        ),
        schema="production",
    )
    op.create_index(
        "ux_extraction_daily_reports_product_date",
        "extraction_daily_reports",
        ["product_code", "report_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ux_extraction_daily_reports_product_date",
        table_name="extraction_daily_reports",
        schema="production",
    )
    op.drop_table("extraction_daily_reports", schema="production")
