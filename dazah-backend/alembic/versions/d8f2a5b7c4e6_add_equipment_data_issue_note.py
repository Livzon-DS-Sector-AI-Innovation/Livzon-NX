"""add equipment data_issue_note

Revision ID: d8f2a5b7c4e6
Revises: c7d1e4f8a2b3
Create Date: 2026-10-10

设备台账导入容错：字段缺失或无法解析（如出厂日期「201年9月」）
不再拒行，改为记录待修正说明，页面上标红提示人工修正。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d8f2a5b7c4e6"
down_revision = "c7d1e4f8a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equipments",
        sa.Column("data_issue_note", sa.Text(), nullable=True),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("equipments", "data_issue_note", schema="equipment")
