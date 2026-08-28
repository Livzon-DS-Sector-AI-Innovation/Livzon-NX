"""add_production_plans

Revision ID: add269737689
Revises: 3279d53f4dab
Create Date: 2026-07-02 11:38:28.758586
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add269737689"
down_revision: str | None = "3279d53f4dab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "production_plans" in inspector.get_table_names(schema="production"):
        return
    op.create_table(
        "production_plans",
        sa.Column("batch_no", sa.String(length=64), nullable=True, comment="批号"),
        sa.Column(
            "product_name", sa.String(length=128), nullable=False, comment="产品名称"
        ),
        sa.Column("workshop", sa.String(length=64), nullable=True, comment="车间"),
        sa.Column("plan_date", sa.Date(), nullable=True, comment="计划日期"),
        sa.Column("unit", sa.String(length=32), nullable=True, comment="单位"),
        sa.Column("planned_yield", sa.Float(), nullable=True, comment="计划产量"),
        sa.Column("actual_completion", sa.Float(), nullable=True, comment="实际完成"),
        sa.Column("completion_rate", sa.Float(), nullable=True, comment="完成率"),
        sa.Column(
            "safety_status", sa.String(length=128), nullable=True, comment="安环情况"
        ),
        sa.Column(
            "quality_status", sa.String(length=128), nullable=True, comment="质量情况"
        ),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
        sa.Column("source", sa.String(length=32), nullable=True, comment="数据来源"),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity.users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["identity.users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_production_plans_product_name",
        "production_plans",
        ["product_name"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_production_plans_plan_date",
        "production_plans",
        ["plan_date"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_production_plans_plan_date",
        table_name="production_plans",
        schema="production",
    )
    op.drop_index(
        "ix_production_plans_product_name",
        table_name="production_plans",
        schema="production",
    )
    op.drop_table("production_plans", schema="production")
