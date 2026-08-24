"""update validation records fields

Revision ID: a7c100000007
Revises: a7c100000006
Create Date: 2026-07-01 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000007"
down_revision: str | None = "a7c100000006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {
        col["name"]
        for col in inspector.get_columns("validation_records", schema="quality")
    }

    # Add new columns
    if "department" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("department", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "equipment_code" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("equipment_code", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "product_codes" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("product_codes", sa.ARRAY(sa.String()), nullable=True),
            schema="quality",
        )
    if "planned_end_date" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("planned_end_date", sa.Date(), nullable=True),
            schema="quality",
        )

    # Drop old columns
    if "responsible_department" in existing_columns:
        op.drop_column("validation_records", "responsible_department", schema="quality")
    if "owner_name" in existing_columns:
        op.drop_column("validation_records", "owner_name", schema="quality")
    if "planned_date" in existing_columns:
        op.drop_column("validation_records", "planned_date", schema="quality")
    if "completed_date" in existing_columns:
        op.drop_column("validation_records", "completed_date", schema="quality")
    if "remarks" in existing_columns:
        op.drop_column("validation_records", "remarks", schema="quality")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {
        col["name"]
        for col in inspector.get_columns("validation_records", schema="quality")
    }

    # Drop new columns
    if "department" in existing_columns:
        op.drop_column("validation_records", "department", schema="quality")
    if "equipment_code" in existing_columns:
        op.drop_column("validation_records", "equipment_code", schema="quality")
    if "product_codes" in existing_columns:
        op.drop_column("validation_records", "product_codes", schema="quality")
    if "planned_end_date" in existing_columns:
        op.drop_column("validation_records", "planned_end_date", schema="quality")

    # Add back old columns
    if "responsible_department" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("responsible_department", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "owner_name" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("owner_name", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "planned_date" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("planned_date", sa.Date(), nullable=True),
            schema="quality",
        )
    if "completed_date" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("completed_date", sa.Date(), nullable=True),
            schema="quality",
        )
    if "remarks" not in existing_columns:
        op.add_column(
            "validation_records",
            sa.Column("remarks", sa.Text(), nullable=True),
            schema="quality",
        )
