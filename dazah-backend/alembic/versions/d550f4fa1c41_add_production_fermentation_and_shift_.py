"""add production fermentation and shift operations

Revision ID: d550f4fa1c41
Revises: 5d2fa1558170
Create Date: 2026-07-15 09:15:26.362772
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d550f4fa1c41"
down_revision: str | None = "5d2fa1558170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "fermentation_records",
        sa.Column("batch_no", sa.String(64), nullable=False),
        sa.Column("product_name", sa.String(100), nullable=False),
        sa.Column("fermenter", sa.String(64), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("discharge_date", sa.Date(), nullable=True),
        sa.Column(
            "cycle_data",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("tank_yield", sa.Float(), nullable=True),
        sa.Column(
            "status", sa.String(32), server_default="in_progress", nullable=False
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("attachment", sa.String(500), nullable=True),
        sa.Column("source", sa.String(32), server_default="manual", nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_fermentation_records_batch_no",
        "fermentation_records",
        ["batch_no"],
        schema="production",
    )
    op.create_index(
        "ix_fermentation_records_product_name",
        "fermentation_records",
        ["product_name"],
        schema="production",
    )

    op.create_table(
        "seed_culture_records",
        sa.Column("batch_no", sa.String(64), nullable=False),
        sa.Column("product_name", sa.String(100), server_default="", nullable=False),
        sa.Column("prepare_date", sa.Date(), nullable=True),
        sa.Column(
            "materials",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "quality_data",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "operation_data",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("tank_yield", sa.Float(), nullable=True),
        sa.Column(
            "status", sa.String(32), server_default="in_progress", nullable=False
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), server_default="manual", nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "source_record_id", name="uq_seed_culture_source_record"
        ),
        schema="production",
    )
    op.create_index(
        "ix_seed_culture_records_batch_no",
        "seed_culture_records",
        ["batch_no"],
        schema="production",
    )
    op.create_index(
        "ix_seed_culture_records_prepare_date",
        "seed_culture_records",
        ["prepare_date"],
        schema="production",
    )

    op.create_table(
        "non_conforming_events",
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restore_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impact_duration", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("workshop", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("impact_scope", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column(
            "related_batch_nos",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_nce_event_time",
        "non_conforming_events",
        ["event_time"],
        schema="production",
    )
    op.create_index(
        "ix_nce_workshop", "non_conforming_events", ["workshop"], schema="production"
    )
    op.create_index(
        "ix_nce_event_type",
        "non_conforming_events",
        ["event_type"],
        schema="production",
    )

    op.create_table(
        "shift_logs",
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.String(16), nullable=False),
        sa.Column("workshop", sa.String(64), nullable=False),
        sa.Column("handover_from", sa.String(64), nullable=False),
        sa.Column("handover_to", sa.String(64), nullable=False),
        sa.Column("production_summary", sa.Text(), nullable=True),
        sa.Column("equipment_status", sa.Text(), nullable=True),
        sa.Column("abnormal_events", sa.Text(), nullable=True),
        sa.Column("pending_tasks", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_shift_logs_date", "shift_logs", ["log_date"], schema="production"
    )
    op.create_index(
        "ix_shift_logs_workshop", "shift_logs", ["workshop"], schema="production"
    )

    op.create_table(
        "shift_handovers",
        sa.Column("position", sa.String(64), nullable=False),
        sa.Column("workshop", sa.String(64), nullable=False),
        sa.Column("shift", sa.String(16), nullable=False),
        sa.Column("handover_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handover_from", sa.String(64), nullable=False),
        sa.Column("handover_to", sa.String(64), nullable=False),
        sa.Column("production_status", sa.Text(), nullable=True),
        sa.Column("equipment_status", sa.Text(), nullable=True),
        sa.Column("equipment_inspection", sa.Text(), nullable=True),
        sa.Column("tools_handover", sa.Text(), nullable=True),
        sa.Column("fire_emergency", sa.Text(), nullable=True),
        sa.Column("ppe_status", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_shift_handovers_handover_time",
        "shift_handovers",
        ["handover_time"],
        schema="production",
    )
    op.create_index(
        "ix_shift_handovers_position",
        "shift_handovers",
        ["position"],
        schema="production",
    )
    op.create_index(
        "ix_shift_handovers_workshop",
        "shift_handovers",
        ["workshop"],
        schema="production",
    )


def downgrade() -> None:
    for table in (
        "shift_handovers",
        "shift_logs",
        "non_conforming_events",
        "seed_culture_records",
        "fermentation_records",
    ):
        op.drop_table(table, schema="production")
