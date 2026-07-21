"""add validation execution tables

Revision ID: a7c100000009
Revises: a7c100000008
Create Date: 2026-07-01 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000009"
down_revision: str | None = "a7c100000008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_execution_table(table_name: str, unique_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("master_validation_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("product_codes", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("group_chat", sa.String(length=255), nullable=True),
        sa.Column("participants", sa.String(length=255), nullable=True),
        sa.Column("owner_name", sa.String(length=100), nullable=True),
        sa.Column("plan_name", sa.String(length=255), nullable=True),
        sa.Column("plan_code", sa.String(length=100), nullable=True),
        sa.Column("drafted_at", sa.Date(), nullable=True),
        sa.Column("approved_at", sa.Date(), nullable=True),
        sa.Column("report_no", sa.String(length=100), nullable=True),
        sa.Column("drafted_at_1", sa.Date(), nullable=True),
        sa.Column("approved_at_1", sa.Date(), nullable=True),
        sa.Column("revalidation_cycle_years", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("master_validation_id", name=unique_name),
        schema="quality",
    )
    op.create_index(
        f"ix_quality_{table_name}_master_validation_id",
        table_name,
        ["master_validation_id"],
        unique=False,
        schema="quality",
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_specs = [
        ("equipment_qualification_records", "uq_equipment_qualification_master_validation_id"),
        ("process_validation_records", "uq_process_validation_master_validation_id"),
        ("cleaning_validation_records", "uq_cleaning_validation_master_validation_id"),
        ("other_validation_records", "uq_other_validation_master_validation_id"),
    ]

    for table_name, unique_name in table_specs:
        if not inspector.has_table(table_name, schema="quality"):
            _create_execution_table(table_name, unique_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in [
        "other_validation_records",
        "cleaning_validation_records",
        "process_validation_records",
        "equipment_qualification_records",
    ]:
        if inspector.has_table(table_name, schema="quality"):
            index_name = f"ix_quality_{table_name}_master_validation_id"
            existing_indexes = {
                index["name"] for index in inspector.get_indexes(table_name, schema="quality")
            }
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name, schema="quality")
            op.drop_table(table_name, schema="quality")
