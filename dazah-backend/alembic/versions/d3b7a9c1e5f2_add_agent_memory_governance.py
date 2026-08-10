"""add Agent memory governance

Revision ID: d3b7a9c1e5f2
Revises: c6d4e8f2a913
Create Date: 2026-08-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3b7a9c1e5f2"
down_revision: str | None = "c6d4e8f2a913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "agent_memory_tenant_policies",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(32), server_default="auto", nullable=False),
        sa.Column("policy_version", sa.Integer(), server_default="1", nullable=False),
        *_base_columns(),
        sa.UniqueConstraint("tenant_id", name="uq_core_agent_memory_tenant_policy"),
        sa.CheckConstraint(
            "mode IN ('auto', 'explicit_only', 'disabled')",
            name="ck_core_agent_memory_tenant_policy_mode",
        ),
        schema="core",
        comment="租户级 Agent 个人记忆上限策略",
    )
    op.create_index(
        "ix_core_agent_memory_tenant_policies_tenant_id",
        "agent_memory_tenant_policies",
        ["tenant_id"],
        schema="core",
    )
    op.create_table(
        "agent_memory_user_preferences",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(32), server_default="auto", nullable=False),
        sa.Column("mode_before_pause", sa.String(32), nullable=True),
        sa.Column(
            "preference_version", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column(
            "notice_sent_version", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("last_cleared_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_core_agent_memory_user_preference"
        ),
        sa.CheckConstraint(
            "mode IN ('auto', 'explicit_only', 'paused')",
            name="ck_core_agent_memory_user_preference_mode",
        ),
        sa.CheckConstraint(
            "mode_before_pause IS NULL OR "
            "mode_before_pause IN ('auto', 'explicit_only')",
            name="ck_core_agent_memory_user_preference_prior_mode",
        ),
        schema="core",
        comment="用户个人记忆模式与删除标记",
    )
    op.create_index(
        "ix_core_agent_memory_user_preferences_tenant_id",
        "agent_memory_user_preferences",
        ["tenant_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_memory_user_preferences_user_id",
        "agent_memory_user_preferences",
        ["user_id"],
        schema="core",
    )
    op.create_table(
        "agent_memory_clear_confirmations",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_base_columns(),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_core_agent_memory_clear_confirmation"
        ),
        schema="core",
        comment="用户清空长期记忆的短期确认",
    )
    op.create_index(
        "ix_core_agent_memory_clear_confirmations_tenant_id",
        "agent_memory_clear_confirmations",
        ["tenant_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_memory_clear_confirmations_user_id",
        "agent_memory_clear_confirmations",
        ["user_id"],
        schema="core",
    )


def downgrade() -> None:
    for table in (
        "agent_memory_clear_confirmations",
        "agent_memory_user_preferences",
        "agent_memory_tenant_policies",
    ):
        op.drop_table(table, schema="core")
