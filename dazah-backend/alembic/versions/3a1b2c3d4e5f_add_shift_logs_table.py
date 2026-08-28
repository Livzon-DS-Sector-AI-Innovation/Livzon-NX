"""add_shift_logs_table

Revision ID: 3a1b2c3d4e5f
Revises: a92e3c435c3b
Create Date: 2026-07-06 11:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a1b2c3d4e5f"
down_revision: str | None = "a92e3c435c3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("shift_logs", schema="production"):
        op.drop_table("shift_logs", schema="production")
    op.create_table(
        "shift_logs",
        sa.Column("log_date", sa.Date(), nullable=False, comment="日期"),
        sa.Column(
            "shift",
            sa.String(length=16),
            nullable=False,
            comment="班次（morning/afternoon/night）",
        ),
        sa.Column("workshop", sa.String(length=64), nullable=False, comment="车间"),
        sa.Column(
            "handover_from", sa.String(length=64), nullable=False, comment="交班人"
        ),
        sa.Column(
            "handover_to", sa.String(length=64), nullable=False, comment="接班人"
        ),
        sa.Column(
            "production_summary", sa.Text(), nullable=True, comment="本班生产情况"
        ),
        sa.Column("equipment_status", sa.Text(), nullable=True, comment="设备运行状况"),
        sa.Column("abnormal_events", sa.Text(), nullable=True, comment="异常情况"),
        sa.Column("pending_tasks", sa.Text(), nullable=True, comment="待办事项交接"),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity.users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["identity.users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_shift_logs_date",
        "shift_logs",
        ["log_date"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_shift_logs_workshop",
        "shift_logs",
        ["workshop"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shift_logs_workshop", table_name="shift_logs", schema="production"
    )
    op.drop_index("ix_shift_logs_date", table_name="shift_logs", schema="production")
    op.drop_table("shift_logs", schema="production")
