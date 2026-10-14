"""Add private user feedback and screenshots.

Revision ID: b4e9f3d7a2c0
Revises: a3d8f2c6e1b9
"""

import sqlalchemy as sa

from alembic import op

revision = "b4e9f3d7a2c0"
down_revision = "a3d8f2c6e1b9"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        *_audit_columns(),
        sa.Column("reporter_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'resolved')", name="ck_feedback_status"
        ),
        schema="core",
    )
    op.create_index(
        "ix_feedback_owner_created",
        "user_feedback",
        ["created_by", "created_at"],
        schema="core",
    )
    op.create_index(
        "ix_feedback_status_created",
        "user_feedback",
        ["status", "created_at"],
        schema="core",
    )
    op.create_table(
        "feedback_screenshots",
        *_audit_columns(),
        sa.Column(
            "feedback_id",
            sa.Uuid(),
            sa.ForeignKey("core.user_feedback.id"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        schema="core",
    )
    op.create_index(
        "ix_core_feedback_screenshots_feedback_id",
        "feedback_screenshots",
        ["feedback_id"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("feedback_screenshots", schema="core")
    op.drop_table("user_feedback", schema="core")
