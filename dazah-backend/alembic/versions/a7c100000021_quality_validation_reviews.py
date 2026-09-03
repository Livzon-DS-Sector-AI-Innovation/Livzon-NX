"""add validation review records and files

Revision ID: a7c100000021
Revises: e2f3a4b5c6d7
Create Date: 2026-09-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000021"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("validation_review_records", schema="quality"):
        op.create_table(
            "validation_review_records",
            sa.Column(
                "title",
                sa.String(length=255),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "review_mode",
                sa.String(length=20),
                nullable=False,
                server_default="upload",
            ),
            sa.Column(
                "status", sa.String(length=50), nullable=False, server_default="draft"
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column("input_snapshot", sa.JSON(), nullable=True),
            sa.Column("output_payload", sa.JSON(), nullable=True),
            sa.Column("job_id", sa.String(length=100), nullable=True),
            sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
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
            schema="quality",
        )

    if not inspector.has_table("validation_review_files", schema="quality"):
        op.create_table(
            "validation_review_files",
            sa.Column("review_id", sa.Uuid(), nullable=False),
            sa.Column(
                "doc_kind", sa.String(length=20), nullable=False, server_default="plan"
            ),
            sa.Column(
                "source", sa.String(length=20), nullable=False, server_default="upload"
            ),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("parsed_text", sa.Text(), nullable=True),
            sa.Column(
                "parse_status",
                sa.String(length=50),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("parse_error", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
            schema="quality",
        )

    file_indexes = {
        index["name"]
        for index in inspector.get_indexes("validation_review_files", schema="quality")
    }
    if "ix_quality_validation_review_files_review_id" not in file_indexes:
        op.create_index(
            "ix_quality_validation_review_files_review_id",
            "validation_review_files",
            ["review_id"],
            unique=False,
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("validation_review_files", schema="quality"):
        file_indexes = {
            index["name"]
            for index in inspector.get_indexes(
                "validation_review_files", schema="quality"
            )
        }
        if "ix_quality_validation_review_files_review_id" in file_indexes:
            op.drop_index(
                "ix_quality_validation_review_files_review_id",
                table_name="validation_review_files",
                schema="quality",
            )
        op.drop_table("validation_review_files", schema="quality")

    if inspector.has_table("validation_review_records", schema="quality"):
        op.drop_table("validation_review_records", schema="quality")
