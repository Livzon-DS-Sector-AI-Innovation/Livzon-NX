"""add production execution plans

Revision ID: 1dedd1302f7e
Revises: f31f6eac4007
Create Date: 2026-07-15 13:31:01.674105
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1dedd1302f7e"
down_revision: str | None = "f31f6eac4007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "production_execution_plans",
        sa.Column("workshop", sa.String(length=64), nullable=True),
        sa.Column("product_name", sa.String(length=128), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("planned_yield", sa.Float(), nullable=True),
        sa.Column("actual_completion", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("safety_status", sa.String(length=128), nullable=True),
        sa.Column("quality_status", sa.String(length=128), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
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
            "source",
            "source_record_id",
            name="uq_production_execution_plans_source_record",
        ),
        schema="production",
    )
    for index_name, column_name in (
        ("ix_production_execution_plans_workshop", "workshop"),
        ("ix_production_execution_plans_product", "product_name"),
        ("ix_production_execution_plans_date", "plan_date"),
    ):
        op.create_index(
            index_name,
            "production_execution_plans",
            [column_name],
            schema="production",
        )


def downgrade() -> None:
    op.drop_table("production_execution_plans", schema="production")
