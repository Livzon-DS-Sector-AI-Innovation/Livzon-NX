"""add_shift_handovers_table

Revision ID: 5b2c3d4e6f7a
Revises: 3a1b2c3d4e5f
Create Date: 2026-07-06 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5b2c3d4e6f7a"
down_revision: str | None = "3a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("shift_handovers", schema="production"):
        op.drop_table("shift_handovers", schema="production")
    op.create_table(
        "shift_handovers",
        sa.Column("position", sa.String(length=64), nullable=False, comment="岗位"),
        sa.Column(
            "handover_time",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="交接时间",
        ),
        sa.Column(
            "handover_from", sa.String(length=64), nullable=False, comment="交班人"
        ),
        sa.Column(
            "handover_to", sa.String(length=64), nullable=False, comment="接班人"
        ),
        sa.Column(
            "production_status", sa.Text(), nullable=True, comment="生产工艺运行情况"
        ),
        sa.Column("equipment_status", sa.Text(), nullable=True, comment="设备运行情况"),
        sa.Column(
            "equipment_inspection", sa.Text(), nullable=True, comment="设备巡检情况"
        ),
        sa.Column("tools_handover", sa.Text(), nullable=True, comment="工、器具移交"),
        sa.Column(
            "fire_emergency", sa.Text(), nullable=True, comment="消防、应急器材情况"
        ),
        sa.Column(
            "ppe_status", sa.Text(), nullable=True, comment="人员劳动防护用品穿戴"
        ),
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
        "ix_shift_handovers_handover_time",
        "shift_handovers",
        ["handover_time"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_shift_handovers_position",
        "shift_handovers",
        ["position"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shift_handovers_position", table_name="shift_handovers", schema="production"
    )
    op.drop_index(
        "ix_shift_handovers_handover_time",
        table_name="shift_handovers",
        schema="production",
    )
    op.drop_table("shift_handovers", schema="production")
