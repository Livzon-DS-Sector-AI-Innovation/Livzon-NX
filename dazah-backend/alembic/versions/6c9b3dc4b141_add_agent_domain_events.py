"""add agent domain events

Revision ID: 6c9b3dc4b141
Revises: ee31e7997cde
Create Date: 2026-07-10 14:07:48.871108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6c9b3dc4b141"
down_revision: str | None = "ee31e7997cde"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_domain_events",
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("event_version", sa.String(length=16), nullable=False),
        sa.Column("subject_type", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column(
            "payload_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default="now()",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_module",
            "idempotency_key",
            name="uq_core_agent_domain_events_source_idempotency",
        ),
        schema="core",
        comment="Livzon versioned cross-module events",
    )
    op.create_index(
        "ix_core_agent_domain_events_correlation",
        "agent_domain_events",
        ["correlation_id", "occurred_at"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_domain_events_correlation_id",
        "agent_domain_events",
        ["correlation_id"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_domain_events_event_type",
        "agent_domain_events",
        ["event_type"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_domain_events_source_module",
        "agent_domain_events",
        ["source_module"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_domain_events_subject_id",
        "agent_domain_events",
        ["subject_id"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_core_agent_domain_events_type_occurred",
        "agent_domain_events",
        ["event_type", "occurred_at"],
        unique=False,
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_domain_events_type_occurred",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_domain_events_subject_id",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_domain_events_source_module",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_domain_events_event_type",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_domain_events_correlation_id",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_domain_events_correlation",
        table_name="agent_domain_events",
        schema="core",
    )
    op.drop_table("agent_domain_events", schema="core")
