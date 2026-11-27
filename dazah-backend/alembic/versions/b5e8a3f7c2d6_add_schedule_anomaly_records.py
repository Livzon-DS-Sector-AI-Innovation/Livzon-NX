"""add_schedule_anomaly_records

Revision ID: b5e8a3f7c2d6
Revises: c3f7a1d9e2b4
Create Date: 2026-11-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e8a3f7c2d6"
down_revision: str | None = "c3f7a1d9e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "schedule_anomaly_records",
        sa.Column(
            "product_code",
            sa.String(length=32),
            server_default="FA",
            nullable=False,
            comment="产品代码（如 FA/MC/DR），记录按产品隔离",
        ),
        sa.Column(
            "batch_no",
            sa.String(length=64),
            nullable=False,
            comment="批号（手填）",
        ),
        sa.Column(
            "tank_no",
            sa.String(length=64),
            nullable=True,
            comment="罐号（选填）",
        ),
        sa.Column(
            "anomaly_type",
            sa.String(length=24),
            nullable=False,
            comment="异常类型：delayed/reduced/reseeded/contamination/other",
        ),
        sa.Column(
            "event_date",
            sa.Date(),
            nullable=False,
            comment="异常发生日期",
        ),
        sa.Column(
            "reason",
            sa.String(length=255),
            nullable=False,
            comment="原因（必填）",
        ),
        sa.Column(
            "remark",
            sa.String(length=255),
            nullable=True,
            comment="备注（选填）",
        ),
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
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_schedule_anomaly_records_product_date",
        "schedule_anomaly_records",
        ["product_code", "event_date"],
        schema="production",
    )
    op.create_index(
        "ix_schedule_anomaly_records_batch",
        "schedule_anomaly_records",
        ["batch_no"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_schedule_anomaly_records_batch",
        table_name="schedule_anomaly_records",
        schema="production",
    )
    op.drop_index(
        "ix_schedule_anomaly_records_product_date",
        table_name="schedule_anomaly_records",
        schema="production",
    )
    op.drop_table("schedule_anomaly_records", schema="production")
