# ruff: noqa: E501
"""add agent push deliveries

Revision ID: ee31e7997cde
Revises: 1420c504cb74
Create Date: 2026-07-10 13:27:40.053208
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ee31e7997cde"
down_revision: str | None = "1420c504cb74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_push_template_versions",
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title_template", sa.String(length=500), nullable=False),
        sa.Column("markdown_template", sa.Text(), nullable=False),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_key", "version", name="uq_core_agent_push_template_versions_key_version"),
        schema="core",
        comment="Livzon push message template snapshots",
    )
    op.create_index("ix_core_agent_push_template_versions_key_status", "agent_push_template_versions", ["template_key", "status"], schema="core")
    op.create_index("ix_core_agent_push_template_versions_template_key", "agent_push_template_versions", ["template_key"], schema="core")
    op.create_table(
        "agent_push_deliveries",
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_run_id", sa.Uuid(), nullable=True),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), server_default="feishu", nullable=False),
        sa.Column("recipient_type", sa.String(length=64), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_ref", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("content_summary", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("external_message_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("aggregation_key", sa.String(length=200), nullable=True),
        sa.Column("incident_key", sa.String(length=200), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("card_action_status", sa.String(length=32), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_core_agent_push_deliveries_idempotency"),
        schema="core",
        comment="Livzon Feishu per-recipient deliveries",
    )
    op.create_index("ix_core_agent_push_deliveries_automation_id", "agent_push_deliveries", ["automation_id"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_recipient_created", "agent_push_deliveries", ["recipient_user_id", "created_at"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_recipient_user_id", "agent_push_deliveries", ["recipient_user_id"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_retry_due", "agent_push_deliveries", ["status", "next_attempt_at"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_run_id", "agent_push_deliveries", ["run_id"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_run_status", "agent_push_deliveries", ["run_id", "status"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_status", "agent_push_deliveries", ["status"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_step_run_id", "agent_push_deliveries", ["step_run_id"], schema="core")
    op.create_index("ix_core_agent_push_deliveries_template_version_id", "agent_push_deliveries", ["template_version_id"], schema="core")


def downgrade() -> None:
    for name in (
        "ix_core_agent_push_deliveries_template_version_id",
        "ix_core_agent_push_deliveries_step_run_id",
        "ix_core_agent_push_deliveries_status",
        "ix_core_agent_push_deliveries_run_status",
        "ix_core_agent_push_deliveries_run_id",
        "ix_core_agent_push_deliveries_retry_due",
        "ix_core_agent_push_deliveries_recipient_user_id",
        "ix_core_agent_push_deliveries_recipient_created",
        "ix_core_agent_push_deliveries_automation_id",
    ):
        op.drop_index(name, table_name="agent_push_deliveries", schema="core")
    op.drop_table("agent_push_deliveries", schema="core")
    op.drop_index("ix_core_agent_push_template_versions_template_key", table_name="agent_push_template_versions", schema="core")
    op.drop_index("ix_core_agent_push_template_versions_key_status", table_name="agent_push_template_versions", schema="core")
    op.drop_table("agent_push_template_versions", schema="core")
