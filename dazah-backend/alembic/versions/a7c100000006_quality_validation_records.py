"""add quality validation records

Revision ID: a7c100000006
Revises: a7c100000005
Create Date: 2026-07-01 10:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000006"
down_revision: str | None = "a7c100000005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("validation_records", schema="quality"):
        op.create_table(
            "validation_records",
            sa.Column("record_type", sa.String(length=50), nullable=False),
            sa.Column("record_code", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=True),
            sa.Column("responsible_department", sa.String(length=100), nullable=True),
            sa.Column("owner_name", sa.String(length=100), nullable=True),
            sa.Column("planned_date", sa.Date(), nullable=True),
            sa.Column("completed_date", sa.Date(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
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
            sa.Column(
                "is_deleted", sa.Boolean(), server_default="false", nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "record_code", name="uq_validation_records_record_code"
            ),
            schema="quality",
        )

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("validation_records", schema="quality")
    }
    if "ix_quality_validation_records_record_type" not in existing_indexes:
        op.create_index(
            "ix_quality_validation_records_record_type",
            "validation_records",
            ["record_type"],
            unique=False,
            schema="quality",
        )
    if "ix_quality_validation_records_status" not in existing_indexes:
        op.create_index(
            "ix_quality_validation_records_status",
            "validation_records",
            ["status"],
            unique=False,
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("validation_records", schema="quality"):
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("validation_records", schema="quality")
        }
        if "ix_quality_validation_records_record_type" in existing_indexes:
            op.drop_index(
                "ix_quality_validation_records_record_type",
                table_name="validation_records",
                schema="quality",
            )
        if "ix_quality_validation_records_status" in existing_indexes:
            op.drop_index(
                "ix_quality_validation_records_status",
                table_name="validation_records",
                schema="quality",
            )
        op.drop_table("validation_records", schema="quality")
