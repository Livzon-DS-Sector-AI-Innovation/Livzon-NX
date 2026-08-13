"""upgrade Agent automation control flow and interactions

Revision ID: e4c8a2f7b190
Revises: d3b7a9c1e5f2
Create Date: 2026-08-10 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e4c8a2f7b190"
down_revision: str | None = "d3b7a9c1e5f2"
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
    op.add_column(
        "agent_automation_runs",
        sa.Column("current_step_key", sa.String(80), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column("resume_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.add_column(
        "agent_automation_runs",
        sa.Column(
            "execution_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        schema="core",
    )
    op.create_index(
        "ix_core_agent_automation_runs_current_step_key",
        "agent_automation_runs",
        ["current_step_key"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_automation_runs_resume_at",
        "agent_automation_runs",
        ["resume_at"],
        schema="core",
    )

    op.create_table(
        "agent_automation_grants",
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column(
            "authorization_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "authorized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        schema="core",
        comment="Version-scoped unattended automation grants",
    )
    for column in ("automation_id", "version_id", "owner_user_id"):
        op.create_index(
            f"ix_core_agent_automation_grants_{column}",
            "agent_automation_grants",
            [column],
            schema="core",
        )
    op.create_index(
        "ix_core_agent_automation_grants_active",
        "agent_automation_grants",
        ["automation_id", "version_id", "status"],
        schema="core",
    )

    op.create_table(
        "agent_feishu_resource_templates",
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_url", sa.Text(), nullable=False),
        sa.Column(
            "resource_ref", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("view_type", sa.String(32), server_default="grid", nullable=False),
        sa.Column(
            "field_schema", postgresql.JSONB(), server_default="[]", nullable=False
        ),
        sa.Column(
            "writable_fields", postgresql.JSONB(), server_default="[]", nullable=False
        ),
        sa.Column(
            "record_mode", sa.String(32), server_default="append", nullable=False
        ),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "validation_summary",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        schema="core",
        comment="Bound Feishu resources for automation",
    )
    op.create_index(
        "ix_core_agent_feishu_resource_templates_owner_user_id",
        "agent_feishu_resource_templates",
        ["owner_user_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_feishu_templates_owner_status",
        "agent_feishu_resource_templates",
        ["owner_user_id", "status"],
        schema="core",
    )

    op.create_table(
        "agent_interaction_requests",
        sa.Column("automation_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("step_key", sa.String(80), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "form_schema", postgresql.JSONB(), server_default="[]", nullable=False
        ),
        sa.Column("prefill", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_message_id", sa.String(128), nullable=True),
        sa.Column(
            "result_summary", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_core_agent_interactions_idempotency"
        ),
        schema="core",
        comment="Channel-neutral form and table interactions",
    )
    for column in (
        "automation_id",
        "run_id",
        "owner_user_id",
        "recipient_user_id",
        "template_id",
    ):
        op.create_index(
            f"ix_core_agent_interaction_requests_{column}",
            "agent_interaction_requests",
            [column],
            schema="core",
        )
    op.create_index(
        "ix_core_agent_interactions_owner_status",
        "agent_interaction_requests",
        ["owner_user_id", "status"],
        schema="core",
    )

    op.create_table(
        "agent_interaction_submissions",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_version", sa.Integer(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("values", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="processing", nullable=False),
        sa.Column(
            "write_receipt", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint(
            "request_id",
            "idempotency_key",
            name="uq_core_agent_submissions_request_idempotency",
        ),
        schema="core",
        comment="Idempotent interaction form submissions",
    )
    op.create_index(
        "ix_core_agent_interaction_submissions_request_id",
        "agent_interaction_submissions",
        ["request_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_interaction_submissions_submitted_by",
        "agent_interaction_submissions",
        ["submitted_by"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_submissions_request",
        "agent_interaction_submissions",
        ["request_id", "created_at"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("agent_interaction_submissions", schema="core")
    op.drop_table("agent_interaction_requests", schema="core")
    op.drop_table("agent_feishu_resource_templates", schema="core")
    op.drop_table("agent_automation_grants", schema="core")
    op.drop_index(
        "ix_core_agent_automation_runs_resume_at",
        table_name="agent_automation_runs",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_automation_runs_current_step_key",
        table_name="agent_automation_runs",
        schema="core",
    )
    op.drop_column("agent_automation_runs", "execution_state", schema="core")
    op.drop_column("agent_automation_runs", "resume_at", schema="core")
    op.drop_column("agent_automation_runs", "current_step_key", schema="core")
