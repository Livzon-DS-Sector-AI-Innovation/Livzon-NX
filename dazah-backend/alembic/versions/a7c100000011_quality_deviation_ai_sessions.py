"""add deviation ai sessions

Revision ID: a7c100000011
Revises: a7c100000010
Create Date: 2026-07-02 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000011"
down_revision: str | None = "a7c100000010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("deviation_ai_sessions", schema="quality"):
        op.create_table(
            "deviation_ai_sessions",
            sa.Column("deviation_id", sa.Uuid(), nullable=False),
            sa.Column("supplement_text", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "attachment_summary", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column("deviation_analysis_payload", sa.JSON(), nullable=True),
            sa.Column("capa_suggestion_payload", sa.JSON(), nullable=True),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column(
                "status", sa.String(length=50), nullable=False, server_default="idle"
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
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
            sa.UniqueConstraint(
                "deviation_id",
                name="uq_quality_deviation_ai_sessions_deviation_id",
            ),
            schema="quality",
        )

    session_indexes = {
        index["name"]
        for index in inspector.get_indexes("deviation_ai_sessions", schema="quality")
    }
    if "ix_quality_deviation_ai_sessions_deviation_id" not in session_indexes:
        op.create_index(
            "ix_quality_deviation_ai_sessions_deviation_id",
            "deviation_ai_sessions",
            ["deviation_id"],
            unique=False,
            schema="quality",
        )

    if not inspector.has_table("deviation_ai_session_attachments", schema="quality"):
        op.create_table(
            "deviation_ai_session_attachments",
            sa.Column("session_id", sa.Uuid(), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("parsed_text", sa.Text(), nullable=True),
            sa.Column("parsed_summary", sa.Text(), nullable=True),
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

    attachment_indexes = {
        index["name"]
        for index in inspector.get_indexes(
            "deviation_ai_session_attachments", schema="quality"
        )
    }
    if (
        "ix_quality_deviation_ai_session_attachments_session_id"
        not in attachment_indexes
    ):
        op.create_index(
            "ix_quality_deviation_ai_session_attachments_session_id",
            "deviation_ai_session_attachments",
            ["session_id"],
            unique=False,
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("deviation_ai_session_attachments", schema="quality"):
        attachment_indexes = {
            index["name"]
            for index in inspector.get_indexes(
                "deviation_ai_session_attachments", schema="quality"
            )
        }
        if (
            "ix_quality_deviation_ai_session_attachments_session_id"
            in attachment_indexes
        ):
            op.drop_index(
                "ix_quality_deviation_ai_session_attachments_session_id",
                table_name="deviation_ai_session_attachments",
                schema="quality",
            )
        op.drop_table("deviation_ai_session_attachments", schema="quality")

    if inspector.has_table("deviation_ai_sessions", schema="quality"):
        session_indexes = {
            index["name"]
            for index in inspector.get_indexes(
                "deviation_ai_sessions", schema="quality"
            )
        }
        if "ix_quality_deviation_ai_sessions_deviation_id" in session_indexes:
            op.drop_index(
                "ix_quality_deviation_ai_sessions_deviation_id",
                table_name="deviation_ai_sessions",
                schema="quality",
            )
        op.drop_table("deviation_ai_sessions", schema="quality")
