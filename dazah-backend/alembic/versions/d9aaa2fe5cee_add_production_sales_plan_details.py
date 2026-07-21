"""add production sales plan details

Revision ID: d9aaa2fe5cee
Revises: 15e3b08711ec
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9aaa2fe5cee"
down_revision: str | None = "15e3b08711ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "sales_plan_details",
        sa.Column(
            "product_name", sa.String(length=128), nullable=False, comment="产品名称"
        ),
        sa.Column("unit", sa.String(length=32), nullable=True, comment="单位"),
        sa.Column(
            "last_month_delivered_uninvoiced",
            sa.Float(),
            nullable=True,
            comment="上月已发货未开票",
        ),
        sa.Column(
            "current_year_delivered",
            sa.Float(),
            nullable=True,
            comment="当年当月发货量",
        ),
        sa.Column(
            "month_planned_delivery",
            sa.Float(),
            nullable=True,
            comment="本月计划发货量",
        ),
        sa.Column(
            "month_delivered_qty", sa.Float(), nullable=True, comment="本月已发货量"
        ),
        sa.Column("undelivered_qty", sa.Float(), nullable=True, comment="未发货量"),
        sa.Column(
            "month_planned_invoice", sa.Float(), nullable=True, comment="本月预计开票量"
        ),
        sa.Column("invoiced_qty", sa.Float(), nullable=True, comment="已开票量"),
        sa.Column(
            "delivery_completion_rate",
            sa.Float(),
            nullable=True,
            comment="本月发货完成率(%)",
        ),
        sa.Column(
            "last_month_end_inventory", sa.Float(), nullable=True, comment="上月底库存"
        ),
        sa.Column(
            "month_planned_capacity", sa.Float(), nullable=True, comment="本月预计产能"
        ),
        sa.Column(
            "month_end_inventory", sa.Float(), nullable=True, comment="本月底库存"
        ),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
            comment="数据来源",
        ),
        sa.Column(
            "source_record_id",
            sa.String(length=128),
            nullable=True,
            comment="来源系统记录标识",
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "source_record_id", name="uq_sales_plan_details_source_record"
        ),
        schema="production",
    )
    op.create_index(
        "ix_sales_plan_details_product",
        "sales_plan_details",
        ["product_name"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sales_plan_details_product",
        table_name="sales_plan_details",
        schema="production",
    )
    op.drop_table("sales_plan_details", schema="production")
