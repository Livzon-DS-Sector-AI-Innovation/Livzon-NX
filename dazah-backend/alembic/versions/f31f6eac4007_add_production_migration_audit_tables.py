"""add production migration audit tables

Revision ID: f31f6eac4007
Revises: d550f4fa1c41
Create Date: 2026-07-15 09:31:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f31f6eac4007"
down_revision: str | None = "d550f4fa1c41"
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
        "migration_runs",
        sa.Column("run_key", sa.String(128), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "input_counts",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("inserted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "report",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("rollback_of", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_production_migration_runs_key"),
        schema="production",
    )
    op.create_index(
        "ix_production_migration_runs_status",
        "migration_runs",
        ["status"],
        schema="production",
    )

    op.create_table(
        "migration_record_maps",
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("target_table", sa.String(128), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "entity",
            "source_record_id",
            name="uq_production_migration_record_map",
        ),
        schema="production",
    )
    op.create_index(
        "ix_production_migration_record_maps_target",
        "migration_record_maps",
        ["target_table", "target_id"],
        schema="production",
    )

    op.create_table(
        "migration_changes",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("map_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("before_fingerprint", sa.String(64), nullable=True),
        sa.Column("after_fingerprint", sa.String(64), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_production_migration_changes_run",
        "migration_changes",
        ["run_id"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_table("migration_changes", schema="production")
    op.drop_table("migration_record_maps", schema="production")
    op.drop_table("migration_runs", schema="production")
