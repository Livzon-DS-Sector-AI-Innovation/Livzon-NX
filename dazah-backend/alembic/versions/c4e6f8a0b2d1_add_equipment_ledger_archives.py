"""add equipment_ledger_archives

Revision ID: c4e6f8a0b2d1
Revises: 807ad84a1158
Create Date: 2026-10-14

设备台账 Excel 上传存档表：保存解析后的全量表格结构、原件路径与
导入结果摘要，供回看历次上传；不影响已导入的台账数据。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c4e6f8a0b2d1"
down_revision = "807ad84a1158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_ledger_archives",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workshop_code",
            sa.String(length=10),
            nullable=False,
            server_default="201-1",
        ),
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
            "import_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
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
        schema="equipment",
    )
    op.create_index(
        "ix_equipment_ledger_archives_created_at",
        "equipment_ledger_archives",
        ["created_at"],
        schema="equipment",
    )
    op.create_index(
        "ix_equipment_ledger_archives_workshop_code",
        "equipment_ledger_archives",
        ["workshop_code"],
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_equipment_ledger_archives_workshop_code",
        table_name="equipment_ledger_archives",
        schema="equipment",
    )
    op.drop_index(
        "ix_equipment_ledger_archives_created_at",
        table_name="equipment_ledger_archives",
        schema="equipment",
    )
    op.drop_table("equipment_ledger_archives", schema="equipment")
