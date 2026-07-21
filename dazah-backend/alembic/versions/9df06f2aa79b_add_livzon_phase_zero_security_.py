"""add livzon phase zero security foundation

Revision ID: 9df06f2aa79b
Revises: b6e4d2f9a1c3
Create Date: 2026-07-10 10:47:38.146830
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9df06f2aa79b"
down_revision: str | None = "b6e4d2f9a1c3"
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
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.add_column(
        "users",
        sa.Column(
            "grant_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="用户模块授权单调递增版本",
        ),
        schema="identity",
    )
    op.add_column(
        "agent_tool_calls",
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        schema="core",
    )
    op.execute(
        "UPDATE core.agent_tool_calls SET correlation_id = id "
        "WHERE correlation_id IS NULL"
    )
    op.alter_column(
        "agent_tool_calls",
        "correlation_id",
        nullable=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_tool_calls_correlation_id",
        "agent_tool_calls",
        ["correlation_id"],
        schema="core",
    )
    op.create_table(
        "user_module_grants",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "data_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("grant_version", sa.Integer(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "module_code",
            name="uq_identity_user_module_grants_user_module",
        ),
        schema="identity",
        comment="用户模块授权事实源",
    )
    op.create_index(
        "ix_identity_user_module_grants_user_status",
        "user_module_grants",
        ["user_id", "status"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_user_module_grants_module_status",
        "user_module_grants",
        ["module_code", "status"],
        schema="identity",
    )

    op.create_table(
        "permission_outbox_events",
        *_base_columns(),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("grant_version", sa.Integer(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "grant_version",
            "event_type",
            name="uq_identity_permission_outbox_user_version_type",
        ),
        schema="identity",
        comment="身份权限变更事务 Outbox",
    )
    op.create_index(
        "ix_identity_permission_outbox_events_event_type",
        "permission_outbox_events",
        ["event_type"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_permission_outbox_events_user_id",
        "permission_outbox_events",
        ["user_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_permission_outbox_status_next",
        "permission_outbox_events",
        ["status", "next_attempt_at"],
        schema="identity",
    )

    op.create_table(
        "agent_access_scope_snapshots",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_grant_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "agent_scope_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "modules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "tool_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "workflow_tool_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("registry_version", sa.String(length=64), nullable=False),
        sa.Column(
            "sync_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", name="uq_core_agent_access_scope_snapshots_user_id"
        ),
        schema="core",
        comment="Livzon 有效访问范围派生快照",
    )
    op.create_index(
        "ix_core_agent_access_scope_snapshots_user_id",
        "agent_access_scope_snapshots",
        ["user_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_access_scope_sync_status",
        "agent_access_scope_snapshots",
        ["sync_status", "source_grant_version"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_tool_calls_correlation_id",
        table_name="agent_tool_calls",
        schema="core",
    )
    op.drop_column("agent_tool_calls", "correlation_id", schema="core")
    op.drop_index(
        "ix_core_agent_access_scope_sync_status",
        table_name="agent_access_scope_snapshots",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_access_scope_snapshots_user_id",
        table_name="agent_access_scope_snapshots",
        schema="core",
    )
    op.drop_table("agent_access_scope_snapshots", schema="core")

    op.drop_index(
        "ix_identity_permission_outbox_status_next",
        table_name="permission_outbox_events",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_permission_outbox_events_user_id",
        table_name="permission_outbox_events",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_permission_outbox_events_event_type",
        table_name="permission_outbox_events",
        schema="identity",
    )
    op.drop_table("permission_outbox_events", schema="identity")

    op.drop_index(
        "ix_identity_user_module_grants_module_status",
        table_name="user_module_grants",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_user_module_grants_user_status",
        table_name="user_module_grants",
        schema="identity",
    )
    op.drop_table("user_module_grants", schema="identity")
    op.drop_column("users", "grant_version", schema="identity")
