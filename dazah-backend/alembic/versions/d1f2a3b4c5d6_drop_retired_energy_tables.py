"""Drop retired energy closing, adjustment and entry-plan tables.

Revision ID: d1f2a3b4c5d6
Revises: c8e4a2f6d9b3

The native ledger no longer exposes period closing, manual adjustments or
generated entry plans. Historical Wiki snapshot tables are intentionally
untouched. Downgrade recreates the retired tables so the revision remains
reversible; it does not restore any data.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d1f2a3b4c5d6"
down_revision = "c8e4a2f6d9b3"
branch_labels = None
depends_on = None

SCHEMA = "energy"


def _standard_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.drop_table("entry_tasks", schema=SCHEMA)
    op.drop_table("entry_plans", schema=SCHEMA)
    op.drop_table("usage_adjustments", schema=SCHEMA)
    op.drop_table("period_locks", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "period_locks",
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        *_standard_columns(),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_energy_lock_month",
        "period_locks",
        ["month"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "usage_adjustments",
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(28, 8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        *_standard_columns(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_energy_usage_adjustments_metric_key",
        "usage_adjustments",
        ["metric_key"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_energy_usage_adjustments_usage_date",
        "usage_adjustments",
        ["usage_date"],
        schema=SCHEMA,
    )

    op.create_table(
        "entry_plans",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        *_standard_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "entry_tasks",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("task_date", sa.Date(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        *_standard_columns(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_energy_entry_tasks_task_date",
        "entry_tasks",
        ["task_date"],
        schema=SCHEMA,
    )
    op.create_index(
        "uq_energy_task_plan_day",
        "entry_tasks",
        ["plan_id", "task_date"],
        unique=True,
        schema=SCHEMA,
    )
