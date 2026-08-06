"""add persistent Agent session attachments

Revision ID: c6d4e8f2a913
Revises: 8b42d1e6f903
Create Date: 2026-08-06 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6d4e8f2a913"
down_revision: str | None = "8b42d1e6f903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_attachments",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        schema="core",
        comment="会话级持久附件及可恢复解析内容",
    )
    op.create_index(
        "ix_core_agent_attachments_session_active",
        "agent_attachments",
        ["session_id", "is_deleted"],
        schema="core",
    )
    for column in ("session_id", "message_id", "user_id", "sha256"):
        op.create_index(
            f"ix_core_agent_attachments_{column}",
            "agent_attachments",
            [column],
            schema="core",
        )


def downgrade() -> None:
    for column in ("sha256", "user_id", "message_id", "session_id"):
        op.drop_index(
            f"ix_core_agent_attachments_{column}",
            table_name="agent_attachments",
            schema="core",
        )
    op.drop_index(
        "ix_core_agent_attachments_session_active",
        table_name="agent_attachments",
        schema="core",
    )
    op.drop_table("agent_attachments", schema="core")
