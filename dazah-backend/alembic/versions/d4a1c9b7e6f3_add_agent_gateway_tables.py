"""add agent gateway tables

Revision ID: d4a1c9b7e6f3
Revises: b9c3d8e1f4a2
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4a1c9b7e6f3"
down_revision: str | None = "b9c3d8e1f4a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default="active", nullable=False
        ),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent conversation sessions",
    )
    op.create_index(
        "ix_core_agent_sessions_user_id", "agent_sessions", ["user_id"], schema="core"
    )

    op.create_table(
        "agent_messages",
        *_base_columns(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "message_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent conversation messages",
    )
    op.create_index(
        "ix_core_agent_messages_session_id",
        "agent_messages",
        ["session_id"],
        schema="core",
    )

    op.create_table(
        "agent_tool_calls",
        *_base_columns(),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="started", nullable=False
        ),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent tool execution audit",
    )
    op.create_index(
        "ix_core_agent_tool_calls_session_id",
        "agent_tool_calls",
        ["session_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_tool_calls_operation",
        "agent_tool_calls",
        ["operation"],
        schema="core",
    )

    op.create_table(
        "agent_confirmations",
        *_base_columns(),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column(
            "risk_level", sa.String(length=32), server_default="medium", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent write operation confirmations",
    )
    op.create_index(
        "ix_core_agent_confirmations_session_id",
        "agent_confirmations",
        ["session_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_confirmations_user_id",
        "agent_confirmations",
        ["user_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_confirmations_operation",
        "agent_confirmations",
        ["operation"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_confirmations_operation",
        table_name="agent_confirmations",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_confirmations_user_id",
        table_name="agent_confirmations",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_confirmations_session_id",
        table_name="agent_confirmations",
        schema="core",
    )
    op.drop_table("agent_confirmations", schema="core")
    op.drop_index(
        "ix_core_agent_tool_calls_operation",
        table_name="agent_tool_calls",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_tool_calls_session_id",
        table_name="agent_tool_calls",
        schema="core",
    )
    op.drop_table("agent_tool_calls", schema="core")
    op.drop_index(
        "ix_core_agent_messages_session_id", table_name="agent_messages", schema="core"
    )
    op.drop_table("agent_messages", schema="core")
    op.drop_index(
        "ix_core_agent_sessions_user_id", table_name="agent_sessions", schema="core"
    )
    op.drop_table("agent_sessions", schema="core")
