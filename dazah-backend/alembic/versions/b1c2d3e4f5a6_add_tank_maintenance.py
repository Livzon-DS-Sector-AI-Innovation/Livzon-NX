"""add tank_maintenance

Revision ID: b1c2d3e4f5a6
Revises: f9a8e7d6c5b4
Create Date: 2026-09-08

发酵罐检修标注表：支撑发酵车间看板的人工"检修维护"状态。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "f9a8e7d6c5b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tank_maintenance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tank_no", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="production",
    )
    op.create_index(
        "ix_tank_maintenance_tank_no",
        "tank_maintenance",
        ["tank_no"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tank_maintenance_tank_no",
        table_name="tank_maintenance",
        schema="production",
    )
    op.drop_table("tank_maintenance", schema="production")
