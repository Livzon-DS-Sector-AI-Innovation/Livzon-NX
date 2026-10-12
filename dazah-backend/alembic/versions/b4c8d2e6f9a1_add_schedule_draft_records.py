"""add schedule draft records

Revision ID: b4c8d2e6f9a1
Revises: a3f5b7c9d1e2
Create Date: 2026-09-30

自动排产草稿生成历史：参数/摘要/校验/逐日快照 + 导出文件，
同参数去重更新；历史仅是过程记录，不生效。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b4c8d2e6f9a1"
down_revision = "a3f5b7c9d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_draft_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_code",
            sa.String(length=32),
            nullable=False,
            server_default="FA",
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("params_hash", sa.String(length=32), nullable=False),
        sa.Column("days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "validation", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("original_path", sa.String(length=512), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            "created_by", sa.Uuid(), sa.ForeignKey("identity.users.id"), nullable=True
        ),
        sa.Column(
            "updated_by", sa.Uuid(), sa.ForeignKey("identity.users.id"), nullable=True
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
        "ix_schedule_draft_records_hash",
        "schedule_draft_records",
        ["product_code", "params_hash"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_schedule_draft_records_hash",
        table_name="schedule_draft_records",
        schema="production",
    )
    op.drop_table("schedule_draft_records", schema="production")
