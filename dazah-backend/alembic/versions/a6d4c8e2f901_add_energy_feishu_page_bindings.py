"""unify module Feishu configuration storage

Revision ID: a6d4c8e2f901
Revises: 9c5e2a7b4d10
Create Date: 2026-07-21 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a6d4c8e2f901"
down_revision: str | None = "9c5e2a7b4d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feishu_configs",
        sa.Column(
            "timezone", sa.String(64), server_default="Asia/Shanghai", nullable=False
        ),
        schema="production",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "daily_sync_time", sa.String(5), server_default="02:00", nullable=False
        ),
        schema="production",
    )
    op.create_table(
        "feishu_page_bindings",
        sa.Column("page_key", sa.String(255), nullable=False),
        sa.Column("sheet_id", sa.Uuid(), nullable=False),
        sa.Column("tab_name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "visible_field_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_key", "sheet_id", "is_deleted", name="uq_energy_feishu_page_binding"
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_feishu_page_bindings_page",
        "feishu_page_bindings",
        ["page_key", "sort_order"],
        schema="energy",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_energy_feishu_page_bindings_page",
        table_name="feishu_page_bindings",
        schema="energy",
    )
    op.drop_table("feishu_page_bindings", schema="energy")
    op.drop_column("feishu_configs", "daily_sync_time", schema="production")
    op.drop_column("feishu_configs", "timezone", schema="production")
