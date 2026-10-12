"""add equipment factory_no and arrival_date

Revision ID: c7d1e4f8a2b3
Revises: b4c8d2e6f9a1
Create Date: 2026-10-09

设备台账字段对齐工厂标准台账：新增出厂编号与入厂日期两列，
均为可空列，不迁移既有数据。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7d1e4f8a2b3"
down_revision = "b4c8d2e6f9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equipments",
        sa.Column("factory_no", sa.String(length=100), nullable=True),
        schema="equipment",
    )
    op.add_column(
        "equipments",
        sa.Column("arrival_date", sa.Date(), nullable=True),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("equipments", "arrival_date", schema="equipment")
    op.drop_column("equipments", "factory_no", schema="equipment")
