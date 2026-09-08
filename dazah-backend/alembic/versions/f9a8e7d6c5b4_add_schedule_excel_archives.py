"""add schedule_excel_archives

Revision ID: f9a8e7d6c5b4
Revises: f8e7d6c5b4a3
Create Date: 2026-09-08

排产计划 Excel 存档表：保存解析后的全量表格结构与原件路径。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f9a8e7d6c5b4"
down_revision = "f8e7d6c5b4a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_excel_archives",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("original_path", sa.String(length=512), nullable=False),
        sa.Column(
            "rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "merges", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "col_widths", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("col_count", sa.Integer(), nullable=False),
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
        "ix_schedule_excel_archives_created_at",
        "schedule_excel_archives",
        ["created_at"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_schedule_excel_archives_created_at",
        table_name="schedule_excel_archives",
        schema="production",
    )
    op.drop_table("schedule_excel_archives", schema="production")
