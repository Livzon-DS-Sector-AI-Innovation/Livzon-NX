"""add quality tracking tables

Revision ID: a7c100000010
Revises: a7c100000009
Create Date: 2026-07-02 16:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000010"
down_revision: str | None = "a7c100000009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table(
        "deviation_investigation_push_records", schema="quality"
    ):
        op.create_table(
            "deviation_investigation_push_records",
            sa.Column("deviation_id", sa.Uuid(), nullable=False),
            sa.Column("deviation_code", sa.String(length=255), nullable=False),
            sa.Column("push_round", sa.String(length=50), nullable=False),
            sa.Column("investigation_report_url", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("submitter", sa.String(length=255), nullable=True),
            sa.Column("department_head", sa.String(length=255), nullable=True),
            sa.Column("department_head_result", sa.String(length=50), nullable=True),
            sa.Column(
                "department_head_reviewed_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column("qa_name", sa.String(length=255), nullable=True),
            sa.Column("qa_result", sa.String(length=50), nullable=True),
            sa.Column("qa_reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("qa_head_name", sa.String(length=255), nullable=True),
            sa.Column("qa_head_result", sa.String(length=50), nullable=True),
            sa.Column("qa_head_reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
    deviation_indexes = {
        index["name"]
        for index in inspector.get_indexes(
            "deviation_investigation_push_records", schema="quality"
        )
    }
    if (
        "ix_quality_deviation_investigation_push_records_deviation_id"
        not in deviation_indexes
    ):
        op.create_index(
            "ix_quality_deviation_investigation_push_records_deviation_id",
            "deviation_investigation_push_records",
            ["deviation_id"],
            unique=False,
            schema="quality",
        )

    if not inspector.has_table("capa_plan_tracks", schema="quality"):
        op.create_table(
            "capa_plan_tracks",
            sa.Column("capa_id", sa.Uuid(), nullable=False),
            sa.Column("capa_code", sa.String(length=255), nullable=False),
            sa.Column("plan_content", sa.Text(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("owner_name", sa.String(length=255), nullable=True),
            sa.Column(
                "owner_confirmed", sa.Boolean(), server_default="false", nullable=False
            ),
            sa.Column("department_head", sa.String(length=255), nullable=True),
            sa.Column(
                "department_head_confirmed",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
            sa.Column("progress", sa.String(length=50), nullable=True),
            sa.Column(
                "reminder_status",
                sa.String(length=50),
                server_default="pending",
                nullable=False,
            ),
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
    capa_indexes = {
        index["name"]
        for index in inspector.get_indexes("capa_plan_tracks", schema="quality")
    }
    if "ix_quality_capa_plan_tracks_capa_id" not in capa_indexes:
        op.create_index(
            "ix_quality_capa_plan_tracks_capa_id",
            "capa_plan_tracks",
            ["capa_id"],
            unique=False,
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("capa_plan_tracks", schema="quality"):
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("capa_plan_tracks", schema="quality")
        }
        if "ix_quality_capa_plan_tracks_capa_id" in existing_indexes:
            op.drop_index(
                "ix_quality_capa_plan_tracks_capa_id",
                table_name="capa_plan_tracks",
                schema="quality",
            )
        op.drop_table("capa_plan_tracks", schema="quality")

    if inspector.has_table("deviation_investigation_push_records", schema="quality"):
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes(
                "deviation_investigation_push_records", schema="quality"
            )
        }
        if (
            "ix_quality_deviation_investigation_push_records_deviation_id"
            in existing_indexes
        ):
            op.drop_index(
                "ix_quality_deviation_investigation_push_records_deviation_id",
                table_name="deviation_investigation_push_records",
                schema="quality",
            )
        op.drop_table("deviation_investigation_push_records", schema="quality")
