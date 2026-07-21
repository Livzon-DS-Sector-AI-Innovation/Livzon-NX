"""add validation detail fields

Revision ID: a7c100000008
Revises: a7c100000007
Create Date: 2026-07-01 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000008"
down_revision: str | None = "a7c100000007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {
        col["name"]
        for col in inspector.get_columns("validation_records", schema="quality")
    }

    # Add new columns for 设备确认/工艺验证/清洁验证/其他验证
    if "group_chat" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("group_chat", sa.String(length=255), nullable=True),
            schema="quality",
        )
    if "participants" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("participants", sa.String(length=255), nullable=True),
            schema="quality",
        )
    if "owner_name" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("owner_name", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "plan_name" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("plan_name", sa.String(length=255), nullable=True),
            schema="quality",
        )
    if "plan_code" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("plan_code", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "drafted_at" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("drafted_at", sa.Date(), nullable=True),
            schema="quality",
        )
    if "approved_at" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("approved_at", sa.Date(), nullable=True),
            schema="quality",
        )
    if "report_no" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("report_no", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "drafted_at_1" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("drafted_at_1", sa.Date(), nullable=True),
            schema="quality",
        )
    if "approved_at_1" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("approved_at_1", sa.Date(), nullable=True),
            schema="quality",
        )
    if "revalidation_cycle_years" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("revalidation_cycle_years", sa.Integer(), nullable=True),
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {
        col["name"]
        for col in inspector.get_columns("validation_records", schema="quality")
    }

    # Drop new columns
    for col_name in [
        "group_chat",
        "participants",
        "owner_name",
        "plan_name",
        "plan_code",
        "drafted_at",
        "approved_at",
        "report_no",
        "drafted_at_1",
        "approved_at_1",
        "revalidation_cycle_years",
    ]:
        if col_name in existing_columns:
            op.drop_column("validation_records", col_name, schema="quality")