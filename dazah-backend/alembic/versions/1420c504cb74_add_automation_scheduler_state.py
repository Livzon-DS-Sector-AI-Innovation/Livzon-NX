"""add automation scheduler state

Revision ID: 1420c504cb74
Revises: 417414f45ad9
Create Date: 2026-07-10 12:55:03.988851
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1420c504cb74"
down_revision: str | None = "417414f45ad9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_automations",
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default="0", nullable=False
        ),
        schema="core",
    )
    op.add_column(
        "agent_automations",
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_triggers",
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_triggers",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_triggers",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.create_index(
        "ix_core_agent_automation_triggers_lease_expires_at",
        "agent_automation_triggers",
        ["lease_expires_at"],
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column(
            "service_actor",
            sa.String(length=80),
            server_default="agent_automation_scheduler",
            nullable=False,
        ),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column(
            "trigger_actor_type",
            sa.String(length=32),
            server_default="system",
            nullable=False,
        ),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column("trigger_actor_id", sa.Uuid(), nullable=True),
        schema="core",
    )
    op.create_index(
        "ix_core_agent_automation_runs_retry_due",
        "agent_automation_runs",
        ["status", "retry_at"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_automation_runs_retry_due",
        table_name="agent_automation_runs",
        schema="core",
    )
    for column in (
        "trigger_actor_id",
        "trigger_actor_type",
        "service_actor",
        "retry_count",
        "retry_at",
        "scheduled_for",
    ):
        op.drop_column("agent_automation_runs", column, schema="core")
    op.drop_index(
        "ix_core_agent_automation_triggers_lease_expires_at",
        table_name="agent_automation_triggers",
        schema="core",
    )
    for column in ("lease_expires_at", "claimed_at", "claim_token"):
        op.drop_column("agent_automation_triggers", column, schema="core")
    op.drop_column("agent_automations", "quarantined_at", schema="core")
    op.drop_column("agent_automations", "consecutive_failures", schema="core")
