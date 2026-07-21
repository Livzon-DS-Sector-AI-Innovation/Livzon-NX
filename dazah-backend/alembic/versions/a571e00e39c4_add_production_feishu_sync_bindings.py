"""add production feishu sync bindings

Revision ID: a571e00e39c4
Revises: d9aaa2fe5cee
Create Date: 2026-07-14 16:06:46.669731
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a571e00e39c4"
down_revision: str | None = "d9aaa2fe5cee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "feishu_sync_bindings",
        sa.Column("config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_name", sa.String(length=128), nullable=False),
        sa.Column("sync_target", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=128), nullable=True),
        sa.Column("workshop_code", sa.String(length=64), nullable=True),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column(
            "field_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "last_status",
            sa.String(length=32),
            server_default="not_run",
            nullable=False,
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "config_id",
            "sync_target",
            "table_id",
            name="uq_production_feishu_sync_bindings_target",
        ),
        schema="production",
    )
    op.create_index(
        "ix_production_feishu_sync_bindings_config",
        "feishu_sync_bindings",
        ["config_id"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "ix_production_feishu_sync_bindings_active",
        "feishu_sync_bindings",
        ["is_active"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_production_feishu_sync_bindings_active",
        table_name="feishu_sync_bindings",
        schema="production",
    )
    op.drop_index(
        "ix_production_feishu_sync_bindings_config",
        table_name="feishu_sync_bindings",
        schema="production",
    )
    op.drop_table("feishu_sync_bindings", schema="production")
