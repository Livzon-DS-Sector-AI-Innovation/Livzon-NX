"""add quality change controls table

Revision ID: a7c100000002
Revises: a7c100000001
Create Date: 2026-06-30 14:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000002"
down_revision: str | None = "a7c100000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names(schema="quality"))

    if "quality_change_controls" in existing_tables:
        return

    op.create_table(
        "quality_change_controls",
        sa.Column("serial_number", sa.String(length=50), nullable=True),
        sa.Column("change_code", sa.String(length=100), nullable=False),
        sa.Column("applicant_department", sa.String(length=100), nullable=True),
        sa.Column("change_object", sa.String(length=255), nullable=True),
        sa.Column("change_content", sa.Text(), nullable=True),
        sa.Column("change_level", sa.String(length=50), nullable=True),
        sa.Column("application_date", sa.Date(), nullable=True),
        sa.Column("planned_approval_date", sa.Date(), nullable=True),
        sa.Column("execution_date", sa.Date(), nullable=True),
        sa.Column("closure_date", sa.Date(), nullable=True),
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
        schema="quality",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names(schema="quality"))
    if "quality_change_controls" in existing_tables:
        op.drop_table("quality_change_controls", schema="quality")