"""add livzon automation phase one models

Revision ID: 12491ff54d46
Revises: 9df06f2aa79b
Create Date: 2026-07-10 12:27:33.570064
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "12491ff54d46"
down_revision: str | None = "9df06f2aa79b"
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
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "agent_automations",
        *_base_columns(),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_session_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scope_type", sa.String(length=32), server_default="mine", nullable=False
        ),
        sa.Column("scope_ref", jsonb, server_default="{}", nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="draft", nullable=False
        ),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("last_run_id", sa.Uuid(), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Livzon versioned automation definitions",
    )
    for name, columns in (
        ("ix_core_agent_automations_owner_user_id", ["owner_user_id"]),
        ("ix_core_agent_automations_source_session_id", ["source_session_id"]),
        ("ix_core_agent_automations_scope_type", ["scope_type"]),
        ("ix_core_agent_automations_status", ["status"]),
        ("ix_core_agent_automations_active_version_id", ["active_version_id"]),
        ("ix_core_agent_automations_owner_status", ["owner_user_id", "status"]),
        ("ix_core_agent_automations_scope_status", ["scope_type", "status"]),
    ):
        op.create_index(name, "agent_automations", columns, schema="core")

    op.create_table(
        "agent_automation_versions",
        *_base_columns(),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=16),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column("definition", jsonb, nullable=False),
        sa.Column("policy_snapshot", jsonb, server_default="{}", nullable=False),
        sa.Column("capability_versions", jsonb, server_default="{}", nullable=False),
        sa.Column("change_summary", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "automation_id", "version", name="uq_core_agent_automation_versions_number"
        ),
        schema="core",
        comment="Immutable Livzon automation snapshots",
    )
    op.create_index(
        "ix_core_agent_automation_versions_automation_id",
        "agent_automation_versions",
        ["automation_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_automation_versions_automation",
        "agent_automation_versions",
        ["automation_id", "version"],
        schema="core",
    )

    op.create_table(
        "agent_automation_triggers",
        *_base_columns(),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="enabled", nullable=False
        ),
        sa.Column("schedule", jsonb, server_default="{}", nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=True),
        sa.Column("event_filter", jsonb, server_default="{}", nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="Asia/Shanghai",
            nullable=False,
        ),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Livzon automation trigger configuration",
    )
    for name, columns in (
        ("ix_core_agent_automation_triggers_automation_id", ["automation_id"]),
        ("ix_core_agent_automation_triggers_trigger_type", ["trigger_type"]),
        ("ix_core_agent_automation_triggers_event_type", ["event_type"]),
        ("ix_core_agent_automation_triggers_due", ["status", "next_fire_at"]),
        ("ix_core_agent_automation_triggers_automation", ["automation_id"]),
    ):
        op.create_index(name, "agent_automation_triggers", columns, schema="core")

    op.create_table(
        "agent_automation_runs",
        *_base_columns(),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="queued", nullable=False
        ),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("input_summary", jsonb, server_default="{}", nullable=False),
        sa.Column("output_summary", jsonb, server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_core_agent_automation_runs_idempotency"
        ),
        schema="core",
        comment="Livzon automation execution instances",
    )
    for name, columns in (
        ("ix_core_agent_automation_runs_automation_id", ["automation_id"]),
        ("ix_core_agent_automation_runs_owner_user_id", ["owner_user_id"]),
        ("ix_core_agent_automation_runs_trigger_id", ["trigger_id"]),
        ("ix_core_agent_automation_runs_version_id", ["version_id"]),
        ("ix_core_agent_automation_runs_status", ["status"]),
        ("ix_core_agent_automation_runs_correlation_id", ["correlation_id"]),
        (
            "ix_core_agent_automation_runs_automation_created",
            ["automation_id", "created_at"],
        ),
        ("ix_core_agent_automation_runs_status_created", ["status", "created_at"]),
    ):
        op.create_index(name, "agent_automation_runs", columns, schema="core")

    op.create_table(
        "agent_step_runs",
        *_base_columns(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_summary", jsonb, server_default="{}", nullable=False),
        sa.Column("output_summary", jsonb, server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "step_key", "attempt", name="uq_core_agent_step_runs_attempt"
        ),
        schema="core",
        comment="Livzon automation step execution records",
    )
    for name, columns in (
        ("ix_core_agent_step_runs_run_id", ["run_id"]),
        ("ix_core_agent_step_runs_operation", ["operation"]),
        ("ix_core_agent_step_runs_status", ["status"]),
        ("ix_core_agent_step_runs_run", ["run_id", "created_at"]),
    ):
        op.create_index(name, "agent_step_runs", columns, schema="core")

    op.create_table(
        "agent_run_events",
        *_base_columns(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "actor_type", sa.String(length=32), server_default="system", nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("payload_summary", jsonb, server_default="{}", nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Livzon automation run timeline events",
    )
    for name, columns in (
        ("ix_core_agent_run_events_run_id", ["run_id"]),
        ("ix_core_agent_run_events_event_type", ["event_type"]),
        ("ix_core_agent_run_events_actor_id", ["actor_id"]),
        ("ix_core_agent_run_events_run_occurred", ["run_id", "occurred_at"]),
        ("ix_core_agent_run_events_type", ["event_type", "occurred_at"]),
    ):
        op.create_index(name, "agent_run_events", columns, schema="core")


def downgrade() -> None:
    _drop_indexes(
        "agent_run_events",
        (
            "ix_core_agent_run_events_type",
            "ix_core_agent_run_events_run_occurred",
            "ix_core_agent_run_events_actor_id",
            "ix_core_agent_run_events_event_type",
            "ix_core_agent_run_events_run_id",
        ),
    )
    op.drop_table("agent_run_events", schema="core")
    _drop_indexes(
        "agent_step_runs",
        (
            "ix_core_agent_step_runs_run",
            "ix_core_agent_step_runs_status",
            "ix_core_agent_step_runs_operation",
            "ix_core_agent_step_runs_run_id",
        ),
    )
    op.drop_table("agent_step_runs", schema="core")
    _drop_indexes(
        "agent_automation_runs",
        (
            "ix_core_agent_automation_runs_status_created",
            "ix_core_agent_automation_runs_automation_created",
            "ix_core_agent_automation_runs_correlation_id",
            "ix_core_agent_automation_runs_status",
            "ix_core_agent_automation_runs_version_id",
            "ix_core_agent_automation_runs_trigger_id",
            "ix_core_agent_automation_runs_owner_user_id",
            "ix_core_agent_automation_runs_automation_id",
        ),
    )
    op.drop_table("agent_automation_runs", schema="core")
    _drop_indexes(
        "agent_automation_triggers",
        (
            "ix_core_agent_automation_triggers_automation",
            "ix_core_agent_automation_triggers_due",
            "ix_core_agent_automation_triggers_event_type",
            "ix_core_agent_automation_triggers_trigger_type",
            "ix_core_agent_automation_triggers_automation_id",
        ),
    )
    op.drop_table("agent_automation_triggers", schema="core")
    _drop_indexes(
        "agent_automation_versions",
        (
            "ix_core_agent_automation_versions_automation",
            "ix_core_agent_automation_versions_automation_id",
        ),
    )
    op.drop_table("agent_automation_versions", schema="core")
    _drop_indexes(
        "agent_automations",
        (
            "ix_core_agent_automations_scope_status",
            "ix_core_agent_automations_owner_status",
            "ix_core_agent_automations_active_version_id",
            "ix_core_agent_automations_status",
            "ix_core_agent_automations_scope_type",
            "ix_core_agent_automations_source_session_id",
            "ix_core_agent_automations_owner_user_id",
        ),
    )
    op.drop_table("agent_automations", schema="core")


def _drop_indexes(table_name: str, names: tuple[str, ...]) -> None:
    for name in names:
        op.drop_index(name, table_name=table_name, schema="core")
